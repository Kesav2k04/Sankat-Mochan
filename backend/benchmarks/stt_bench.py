"""
Unified STT benchmark — every model on one audio folder, scored by WER/CER.

Models: faster-whisper (small, medium) + AI4Bharat IndicConformer (CTC, RNNT).
Language is FORCED from references.json per clip (so Whisper can't misdetect).
With references we report WER + CER (CER is the fair metric for Indic scripts).

Usage:
    python stt_bench.py                # uses ./audio
    python stt_bench.py fleurs         # uses ./fleurs (ground-truthed FLEURS set)

references.json in the folder:
    { "ta_0.wav": {"lang": "ta", "text": "..."}, ... }
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

BASE = Path(__file__).parents[1]
AUDIO_DIR = BASE / (sys.argv[1] if len(sys.argv) > 1 else "audio")
FW_MODELS = ["small", "medium"]
AUDIO_EXT = {".wav", ".m4a", ".mp3", ".flac", ".ogg", ".opus", ".aac"}
INDIC_ID = "ai4bharat/indic-conformer-600m-multilingual"

_PUNCT = re.compile(r"[.,!?;:।॥\"'`()\[\]{}—–\-]")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", _PUNCT.sub(" ", s.strip())).strip()


def score(ref: str, hyp: str):
    import jiwer
    r, h = norm(ref), norm(hyp)
    if not r:
        return None, None
    return round(jiwer.wer(r, h) * 100, 1), round(jiwer.cer(r, h) * 100, 1)


def load_wav_mono16k(path: Path):
    data, sr = sf.read(str(path), dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    return np.ascontiguousarray(data), sr


def find_audio():
    return sorted(p for p in AUDIO_DIR.iterdir() if p.suffix.lower() in AUDIO_EXT)


def aggregate(name, rows):
    wers = [w for *_, w, c, _ in rows if w is not None]
    cers = [c for *_, w, c, _ in rows if c is not None]
    lats = [ms for _, _, ms, *_ in rows]
    return {
        "model": name,
        "avg_wer": round(statistics.mean(wers), 1) if wers else None,
        "avg_cer": round(statistics.mean(cers), 1) if cers else None,
        "avg_ms": round(statistics.mean(lats)) if lats else None,
        "rows": rows,  # (name, lang, ms, wer, cer, text)
    }


def run_faster_whisper(size, files, refs):
    from faster_whisper import WhisperModel
    model = WhisperModel(size, device="cpu", compute_type="int8")
    rows = []
    for p in files:
        ref = refs.get(p.name, {})
        lang = ref.get("lang")
        t = time.perf_counter()
        segs, _ = model.transcribe(str(p), language=lang, beam_size=5)
        text = "".join(s.text for s in segs).strip()
        ms = int((time.perf_counter() - t) * 1000)
        w, c = score(ref.get("text", ""), text) if ref.get("text") else (None, None)
        rows.append((p.name, lang or "auto", ms, w, c, text))
    return aggregate(f"faster-whisper-{size}", rows)


def run_indic(mode, files, refs):
    import torch
    import torchaudio
    from transformers import AutoModel
    model = AutoModel.from_pretrained(INDIC_ID, trust_remote_code=True)
    rows = []
    for p in files:
        ref = refs.get(p.name, {})
        lang = ref.get("lang", "hi")
        data, sr = load_wav_mono16k(p)
        wav = torch.from_numpy(data).unsqueeze(0)
        if sr != 16000:
            wav = torchaudio.functional.resample(wav, sr, 16000)
        t = time.perf_counter()
        out = model(wav, lang, mode)
        ms = int((time.perf_counter() - t) * 1000)
        text = (out if isinstance(out, str) else str(out)).strip()
        w, c = score(ref.get("text", ""), text) if ref.get("text") else (None, None)
        rows.append((p.name, lang, ms, w, c, text))
    return aggregate(f"indic-conformer-{mode}", rows)


def main():
    if not AUDIO_DIR.is_dir():
        print(f"No such folder: {AUDIO_DIR}")
        return
    files = find_audio()
    if not files:
        print(f"No audio in {AUDIO_DIR}")
        return
    refs = json.loads((AUDIO_DIR / "references.json").read_text()) if (AUDIO_DIR / "references.json").exists() else {}
    print(f"STT benchmark · dir={AUDIO_DIR.name} · {len(files)} clips · refs={'yes' if refs else 'no'}\n")

    results = []
    for size in FW_MODELS:
        print(f"  faster-whisper-{size} …", flush=True)
        results.append(run_faster_whisper(size, files, refs))
    for mode in ["ctc", "rnnt"]:
        print(f"  indic-conformer-{mode} …", flush=True)
        results.append(run_indic(mode, files, refs))

    have_refs = any(r["avg_cer"] is not None for r in results)
    if have_refs:
        results.sort(key=lambda r: (r["avg_cer"] is None, r["avg_cer"] or 1e9))

    print("\n" + "=" * 74)
    print(f"{'model':<26}{'WER%':>9}{'CER%':>9}{'avg ms':>10}")
    print("-" * 74)
    for r in results:
        w = r["avg_wer"] if r["avg_wer"] is not None else "—"
        c = r["avg_cer"] if r["avg_cer"] is not None else "—"
        print(f"{r['model']:<26}{str(w):>9}{str(c):>9}{r['avg_ms']:>10}")
    print("=" * 74)
    if have_refs:
        print(f"\n🏆 lowest CER: {results[0]['model']}  (CER {results[0]['avg_cer']}%, {results[0]['avg_ms']}ms)\n")

    for r in results:
        print(f"── {r['model']} ──")
        for name, lang, ms, w, c, text in r["rows"]:
            tag = f"WER {w}% CER {c}%" if w is not None else "no-ref"
            print(f"  {name} [{lang}] {ms}ms {tag}")
            print(f"     {text[:90]}")
        print()


if __name__ == "__main__":
    main()
