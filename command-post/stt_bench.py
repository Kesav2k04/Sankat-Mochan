"""
STT benchmark — compare offline speech-to-text models on Indian-language audio.

Drop audio files into command-post/audio/ (wav/m4a/mp3). Optionally add
audio/references.json to score accuracy (WER/CER):

    {
      "tamil_sos.wav":  {"lang": "ta", "text": "வீடு முழுகிக்கிட்டு இருக்கு ..."},
      "hindi_sos.m4a":  {"lang": "hi", "text": "मेरी माँ को साँस लेने में ..."}
    }

'lang' is optional — it forces the decode language (usually more accurate than
auto-detect). 'text' is the ground-truth transcript for WER.

Run:  python stt_bench.py

Starts with faster-whisper (MIT) sizes. AI4Bharat IndicConformer (best Indic)
can be added as another backend once its runtime is installed.
"""
from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

AUDIO_DIR = Path(__file__).parent / "audio"
# faster-whisper multilingual sizes to compare (small→medium→large climbs accuracy + cost)
FW_MODELS = ["small", "medium"]

AUDIO_EXT = {".wav", ".m4a", ".mp3", ".flac", ".ogg", ".opus", ".aac"}


def load_refs() -> dict:
    f = AUDIO_DIR / "references.json"
    return json.loads(f.read_text()) if f.exists() else {}


def find_audio() -> list[Path]:
    return sorted(p for p in AUDIO_DIR.iterdir() if p.suffix.lower() in AUDIO_EXT)


def norm(s: str) -> str:
    return " ".join(s.strip().lower().split())


def run_faster_whisper(size: str, files: list[Path], refs: dict) -> dict:
    from faster_whisper import WhisperModel
    import jiwer

    model = WhisperModel(size, device="cpu", compute_type="int8")
    rows, wers, lats = [], [], []
    for path in files:
        ref = refs.get(path.name, {})
        lang = ref.get("lang")  # None → auto-detect
        t = time.perf_counter()
        segments, info = model.transcribe(str(path), language=lang, beam_size=5)
        text = "".join(seg.text for seg in segments).strip()  # consume generator = run
        ms = int((time.perf_counter() - t) * 1000)
        lats.append(ms)
        wer = None
        if ref.get("text"):
            wer = round(jiwer.wer(norm(ref["text"]), norm(text)) * 100, 1)
            wers.append(wer)
        rows.append((path.name, info.language, ms, wer, text[:90]))
    return {
        "model": f"faster-whisper-{size}",
        "avg_ms": round(statistics.mean(lats)) if lats else None,
        "avg_wer": round(statistics.mean(wers), 1) if wers else None,
        "rows": rows,
    }


def main() -> None:
    files = find_audio()
    if not files:
        print(f"No audio in {AUDIO_DIR}. Drop wav/m4a/mp3 files there (and optionally references.json).")
        return
    refs = load_refs()
    print(f"STT benchmark · {len(files)} clip(s) · refs={'yes' if refs else 'no (transcripts only)'}\n")
    for p in files:
        print(f"  clip: {p.name}  ({refs.get(p.name, {}).get('lang', 'auto')})")
    print()

    results = []
    for size in FW_MODELS:
        print(f"  running faster-whisper-{size} …", flush=True)
        results.append(run_faster_whisper(size, files, refs))

    # Rank by WER if we have references, else by speed.
    if any(r["avg_wer"] is not None for r in results):
        results.sort(key=lambda r: (r["avg_wer"] is None, r["avg_wer"] or 1e9))
        metric = "avg WER% (lower=better)"
    else:
        results.sort(key=lambda r: r["avg_ms"] or 1e9)
        metric = "avg ms (no refs → speed only)"

    print("\n" + "=" * 68)
    print(f"{'model':<24}{'avg WER%':>12}{'avg ms':>12}   [{metric}]")
    print("-" * 68)
    for r in results:
        w = r["avg_wer"] if r["avg_wer"] is not None else "—"
        print(f"{r['model']:<24}{str(w):>12}{r['avg_ms']:>12}")
    print("=" * 68)

    for r in results:
        print(f"\n── {r['model']} ──")
        for name, lang, ms, wer, text in r["rows"]:
            wtag = f"WER {wer}%" if wer is not None else "no-ref"
            print(f"  {name} [{lang}] {ms}ms {wtag}")
            print(f"     {text}")


if __name__ == "__main__":
    main()
