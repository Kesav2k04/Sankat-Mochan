"""
Auto-detect STT benchmark — the test the normal bench does NOT do.

stt_bench.py forces the language from references.json, so it never measures the
thing we actually care about for the mesh app: "can it figure out the language
by itself?". This harness measures exactly that, for two options:

  Option A  Whisper (faster-whisper small), language=None  → end-to-end auto-detect
  Option B  VoxLingua107 SLID  →  detected lang  →  IndicConformer CTC (two-stage)

For each clip we report: detected lang vs true lang (LID hit/miss), WER, CER,
and latency (Option B splits SLID vs ASR). Ground truth comes from FLEURS
references.json (lang + text).

Usage:  python autodetect_bench.py            # uses ./fleurs
        python autodetect_bench.py audio      # any folder with references.json
"""
from __future__ import annotations

import json
import re
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

BASE = Path(__file__).parents[1]
AUDIO_DIR = BASE / (sys.argv[1] if len(sys.argv) > 1 else "fleurs")
WHISPER_SIZE = "small"
INDIC_ID = "ai4bharat/indic-conformer-600m-multilingual"
VOXLINGUA_ID = "speechbrain/lang-id-voxlingua107-ecapa"

_PUNCT = re.compile(r"[.,!?;:।॥\"'`()\[\]{}—–\-]")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", _PUNCT.sub(" ", s.strip())).strip()


def score(ref: str, hyp: str):
    import jiwer
    r, h = norm(ref), norm(hyp)
    if not r:
        return None, None
    return round(jiwer.wer(r, h) * 100, 1), round(jiwer.cer(r, h) * 100, 1)


def load_wav_16k(path: Path) -> torch.Tensor:
    data, sr = sf.read(str(path), dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    if sr != 16000:  # linear-interp resample (avoids torchaudio's broken ext)
        n_out = int(len(data) * 16000 / sr)
        data = np.interp(
            np.linspace(0, 1, n_out, endpoint=False),
            np.linspace(0, 1, len(data), endpoint=False),
            data,
        ).astype("float32")
    return torch.from_numpy(np.ascontiguousarray(data)).unsqueeze(0)


def find_audio(refs: dict) -> list[Path]:
    return sorted(AUDIO_DIR / name for name in refs if (AUDIO_DIR / name).exists())


# ── Option A ────────────────────────────────────────────────────────────────
def run_whisper_auto(files, refs):
    from faster_whisper import WhisperModel
    model = WhisperModel(WHISPER_SIZE, device="cpu", compute_type="int8")
    rows = []
    for p in files:
        ref = refs[p.name]
        t = time.perf_counter()
        segs, info = model.transcribe(str(p), language=None, beam_size=5)  # auto-detect
        text = "".join(s.text for s in segs).strip()
        ms = int((time.perf_counter() - t) * 1000)
        det = info.language
        w, c = score(ref["text"], text)
        rows.append({
            "name": p.name, "true": ref["lang"], "det": det,
            "hit": det == ref["lang"], "wer": w, "cer": c,
            "lid_ms": None, "asr_ms": ms, "text": text,
        })
    return rows


# ── Option B ────────────────────────────────────────────────────────────────
# VoxLingua107 returns ISO codes; all five FLEURS langs are in its 107-label set.
def run_slid_indic(files, refs):
    from speechbrain.inference.classifiers import EncoderClassifier
    from transformers import AutoModel

    slid = EncoderClassifier.from_hparams(
        source=VOXLINGUA_ID, savedir="pretrained_models/voxlingua107"
    )
    indic = AutoModel.from_pretrained(INDIC_ID, trust_remote_code=True)
    supported = {"hi", "bn", "ta", "te", "kn", "ml", "mr", "gu", "pa", "as", "or", "ur"}

    rows = []
    for p in files:
        ref = refs[p.name]
        wav = load_wav_16k(p)

        t = time.perf_counter()
        pred = slid.classify_batch(wav)  # (out_prob, score, index, text_lab)
        det = pred[3][0].split(":")[0].strip()  # label is 'hi: Hindi' → 'hi'
        lid_ms = int((time.perf_counter() - t) * 1000)

        lang_for_asr = det if det in supported else "hi"  # fall back if LID picks non-Indic
        t = time.perf_counter()
        out = indic(wav, lang_for_asr, "ctc")
        asr_ms = int((time.perf_counter() - t) * 1000)
        text = (out if isinstance(out, str) else str(out)).strip()

        w, c = score(ref["text"], text)
        rows.append({
            "name": p.name, "true": ref["lang"], "det": det,
            "hit": det == ref["lang"], "wer": w, "cer": c,
            "lid_ms": lid_ms, "asr_ms": asr_ms, "text": text,
        })
    return rows


def summarize(label, rows):
    hits = sum(r["hit"] for r in rows)
    cers = [r["cer"] for r in rows if r["cer"] is not None]
    wers = [r["wer"] for r in rows if r["wer"] is not None]
    lids = [r["lid_ms"] for r in rows if r["lid_ms"] is not None]
    asrs = [r["asr_ms"] for r in rows if r["asr_ms"] is not None]
    print(f"\n{'=' * 78}\n{label}\n{'=' * 78}")
    hdr = f"{'clip':<10}{'true':>5}{'det':>6}{'LID':>5}{'WER%':>8}{'CER%':>8}{'lid ms':>9}{'asr ms':>9}"
    print(hdr)
    print("-" * 78)
    for r in rows:
        mark = "✓" if r["hit"] else "✗"
        lid = r["lid_ms"] if r["lid_ms"] is not None else "—"
        print(f"{r['name']:<10}{r['true']:>5}{r['det']:>6}{mark:>5}"
              f"{str(r['wer']):>8}{str(r['cer']):>8}{str(lid):>9}{r['asr_ms']:>9}")
    print("-" * 78)
    print(f"LID accuracy: {hits}/{len(rows)} ({round(100 * hits / len(rows))}%)   "
          f"avg WER {round(statistics.mean(wers), 1) if wers else '—'}%   "
          f"avg CER {round(statistics.mean(cers), 1) if cers else '—'}%   "
          f"avg LID {round(statistics.mean(lids)) if lids else '—'}ms   "
          f"avg ASR {round(statistics.mean(asrs)) if asrs else '—'}ms")
    return {"label": label, "lid_acc": hits / len(rows),
            "cer": statistics.mean(cers) if cers else None,
            "lid_ms": statistics.mean(lids) if lids else None,
            "asr_ms": statistics.mean(asrs) if asrs else None}


def main():
    refs_path = AUDIO_DIR / "references.json"
    if not refs_path.exists():
        print(f"No references.json in {AUDIO_DIR}")
        return
    refs = json.loads(refs_path.read_text())
    files = find_audio(refs)
    print(f"Auto-detect STT benchmark · dir={AUDIO_DIR.name} · {len(files)} clips\n")

    print("→ Option A: Whisper auto-detect (loading faster-whisper-small)…", flush=True)
    a_rows = run_whisper_auto(files, refs)
    a = summarize("Option A · Whisper small (language=None, one model)", a_rows)

    print("\n→ Option B: VoxLingua107 SLID → IndicConformer (loading models)…", flush=True)
    b_rows = run_slid_indic(files, refs)
    b = summarize("Option B · VoxLingua107 SLID → IndicConformer CTC (two-stage)", b_rows)

    print(f"\n{'#' * 78}\nVERDICT\n{'#' * 78}")
    for r in (a, b):
        tot = (r["lid_ms"] or 0) + (r["asr_ms"] or 0)
        print(f"  {r['label']}")
        print(f"      LID {round(100 * r['lid_acc'])}%   CER {round(r['cer'], 1) if r['cer'] is not None else '—'}%   "
              f"~{round(tot)}ms/clip (CPU)")


if __name__ == "__main__":
    main()
