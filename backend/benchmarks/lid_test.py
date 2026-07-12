"""
Test CTC-confidence language ID: can we pick the language from IndicConformer's own logits,
with NO separate SLID model? The encoder is language-agnostic; each language is just a mask
over the 5633 CTC classes. For each language we log_softmax over its masked columns and score
the greedy path's average max log-prob — the language the model is most confident in wins.

Compares against VoxLingua107 SLID (90% on this set). Run: python lid_test.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
import soundfile as sf
import torch

SNAP = Path.home() / (
    ".cache/huggingface/hub/models--ai4bharat--indic-conformer-600m-multilingual/"
    "snapshots/e9b71b369c048e2c6b634d4c131061c34e441179"
)
FLEURS = Path(__file__).parents[1] / "fleurs"
BLANK_ID = 256


def log_softmax(x, axis=-1):
    m = x.max(axis=axis, keepdims=True)
    e = np.exp(x - m)
    return (x - m) - np.log(e.sum(axis=axis, keepdims=True))


def score_language(logprobs, mask_idx):
    """Greedy-path confidence for one language: mean over frames of the max masked log-prob,
    ignoring frames where blank wins (silence/transitions carry no language signal)."""
    sub = logprobs[:, mask_idx]               # (T, n_lang_classes)
    ls = log_softmax(sub, axis=-1)            # log-softmax over just this language's classes
    top = ls.max(axis=-1)                     # (T,) chosen-token log-prob per frame
    arg = ls.argmax(axis=-1)                  # (T,)
    keep = arg != BLANK_ID                    # non-blank frames only
    return top[keep].mean() if keep.any() else -1e9


def main():
    pre = torch.jit.load(str(SNAP / "assets/preprocessor.ts"), map_location="cpu")
    enc = ort.InferenceSession(str(SNAP / "assets/encoder.onnx"), providers=["CPUExecutionProvider"])
    ctc = ort.InferenceSession(str(SNAP / "assets/ctc_decoder.onnx"), providers=["CPUExecutionProvider"])
    masks = json.loads((SNAP / "assets/language_masks.json").read_text())
    refs = json.loads((FLEURS / "references.json").read_text())

    mask_idx = {lang: np.where(np.array(masks[lang], dtype=bool))[0] for lang in masks}
    fleurs_langs = sorted({v["lang"] for v in refs.values()})
    all_langs = sorted(masks.keys())

    def eval_over(candidate_langs, title):
        hits = 0
        rows = []
        for name, ref in refs.items():
            p = FLEURS / name
            if not p.exists():
                continue
            x, sr = sf.read(str(p), dtype="float32")
            wav = torch.from_numpy(x).unsqueeze(0)
            feat, length = pre(input_signal=wav, length=torch.tensor([len(x)]))
            outs, _ = enc.run(["outputs", "encoded_lengths"],
                              {"audio_signal": feat.numpy(), "length": length.numpy()})
            logp = ctc.run(["logprobs"], {"encoder_output": outs})[0][0]  # (T,5633)
            scores = {l: score_language(logp, mask_idx[l]) for l in candidate_langs}
            pick = max(scores, key=scores.get)
            ok = pick == ref["lang"]
            hits += ok
            rows.append((name, ref["lang"], pick, ok))
        print(f"\n=== {title} ({len(candidate_langs)} candidate langs) ===")
        for name, true, pick, ok in rows:
            print(f"  {name:<10} true={true} pick={pick} {'✓' if ok else '✗'}")
        print(f"  LID accuracy: {hits}/{len(rows)} ({round(100*hits/len(rows))}%)")

    eval_over(fleurs_langs, "restricted to the 5 FLEURS languages")
    eval_over(all_langs, "open set: all 22 Indic languages")


if __name__ == "__main__":
    main()
