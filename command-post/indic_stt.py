"""
AI4Bharat IndicConformer-600M (multilingual) transcription test.

Indic-specific ASR (22 Indian languages, MIT). Unlike Whisper it does NOT
auto-detect — you pass the language code. So we transcribe sos1/sos2 with their
(inferred) languages, and for the unknown sos3 we sweep several languages and
show them all so we can spot the right one.

Run:  python indic_stt.py
"""
from __future__ import annotations

import time
from pathlib import Path

import torch
import torchaudio
from transformers import AutoModel

AUDIO = Path(__file__).parent / "audio"
MODEL_ID = "ai4bharat/indic-conformer-600m-multilingual"

print(f"loading {MODEL_ID} (first run downloads ~2.4GB)…", flush=True)
model = AutoModel.from_pretrained(MODEL_ID, trust_remote_code=True)
print("loaded.\n", flush=True)


def load_wav(path: Path) -> torch.Tensor:
    wav, sr = torchaudio.load(str(path))
    wav = torch.mean(wav, dim=0, keepdim=True)  # mono
    if sr != 16000:
        wav = torchaudio.transforms.Resample(orig_freq=sr, new_freq=16000)(wav)
    return wav


def transcribe(path: Path, lang: str, mode: str = "ctc") -> tuple[str, int]:
    wav = load_wav(path)
    t = time.perf_counter()
    out = model(wav, lang, mode)
    ms = int((time.perf_counter() - t) * 1000)
    text = out if isinstance(out, str) else str(out)
    return text.strip(), ms


# sos1 sounded Gujarati, sos2 Hindi (from the Whisper pass). sos3 unknown → sweep.
KNOWN = [("sos1.wav", "gu"), ("sos2.wav", "hi")]
SWEEP_LANGS = ["ta", "ml", "te", "kn", "hi", "gu", "mr", "bn"]

print("=== known-language clips (CTC + RNNT) ===")
for fname, lang in KNOWN:
    p = AUDIO / fname
    if not p.exists():
        continue
    ctc, ms1 = transcribe(p, lang, "ctc")
    rnnt, ms2 = transcribe(p, lang, "rnnt")
    print(f"\n{fname}  lang={lang}")
    print(f"  CTC  ({ms1}ms): {ctc}")
    print(f"  RNNT ({ms2}ms): {rnnt}")

print("\n=== sos3.wav — language sweep (CTC) ===")
p3 = AUDIO / "sos3.wav"
if p3.exists():
    for lang in SWEEP_LANGS:
        try:
            txt, ms = transcribe(p3, lang, "ctc")
            print(f"  [{lang}] ({ms}ms): {txt}")
        except Exception as e:
            print(f"  [{lang}] ERROR: {e}")
