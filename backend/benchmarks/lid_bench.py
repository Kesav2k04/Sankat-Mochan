"""
Language-ID benchmark for the CommandPost — measures the EXACT production code
(stt._identify_from_wav), not a reimplementation. This is the thing that decides
which vocabulary IndicConformer decodes with; if it's wrong the transcript is
garbage, so it is the highest-leverage accuracy lever in the pipeline.

Reports, brutally:
  · overall LID accuracy
  · per-language accuracy (where does it fail?)
  · confusion matrix (what does it confuse for what? — hi/ur, mr/hi, etc.)
  · top1−top2 score margin for correct vs wrong calls (is a confidence
    threshold + fallback worth adding?)

Ground truth: fleurs/references.json (run download_fleurs.py first).

Usage:  python lid_bench.py            # uses ./fleurs
        python lid_bench.py audio      # any folder with references.json
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ modules

import stt

# Windows' default cp1252 stdout can't encode the █ bars or Devanagari in this report
# (raises UnicodeEncodeError mid-run). Force UTF-8 so the benchmark never crashes on output.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001 — best-effort; older/redirected streams may lack reconfigure
    pass

BASE = Path(__file__).parents[1]
AUDIO_DIR = BASE / (sys.argv[1] if len(sys.argv) > 1 else "fleurs")


def load_wav(path: Path) -> torch.Tensor:
    """16 kHz mono float32 → [1, n]. FLEURS is already 16 k; resample defensively."""
    data, sr = sf.read(str(path), dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    if sr != 16000:
        n = int(len(data) * 16000 / sr)
        data = np.interp(
            np.linspace(0, 1, n, endpoint=False),
            np.linspace(0, 1, len(data), endpoint=False),
            data,
        ).astype("float32")
    return torch.from_numpy(np.ascontiguousarray(data)).unsqueeze(0)


def main() -> None:
    refs_path = AUDIO_DIR / "references.json"
    if not refs_path.exists():
        print(f"No references.json in {AUDIO_DIR} — run download_fleurs.py first.")
        return
    refs = json.loads(refs_path.read_text(encoding="utf-8"))
    clips = sorted((AUDIO_DIR / n, r) for n, r in refs.items() if (AUDIO_DIR / n).exists())
    if not clips:
        print(f"No audio for the references in {AUDIO_DIR}.")
        return

    print(f"LID benchmark · dir={AUDIO_DIR.name} · {len(clips)} clips · "
          f"candidates={stt.LID_CANDIDATES}\n", flush=True)
    model = stt._ensure_model()

    rows = []            # (name, true, pred, margin, ms, correct)
    confusion = defaultdict(lambda: defaultdict(int))  # true -> pred -> count
    for path, ref in clips:
        true = ref["lang"]
        wav = load_wav(path)
        t = time.perf_counter()
        out = stt._identify_from_wav(model, wav)
        ms = int((time.perf_counter() - t) * 1000)
        pred = out["lang"]
        scores = out.get("scores", {})
        # margin: gap between best and runner-up (0 if degraded to default with no scores)
        ordered = sorted(scores.values(), reverse=True)
        margin = round(ordered[0] - ordered[1], 3) if len(ordered) >= 2 else 0.0
        correct = pred == true
        confusion[true][pred] += 1
        rows.append((path.name, true, pred, margin, ms, correct))

    # ── overall + per-language ────────────────────────────────────────────────
    hits = sum(r[5] for r in rows)
    print("=" * 60)
    print(f"OVERALL LID accuracy: {hits}/{len(rows)} = {100 * hits / len(rows):.1f}%")
    print(f"avg latency: {round(statistics.mean(r[4] for r in rows))} ms/clip")
    print("=" * 60)

    per_lang = defaultdict(lambda: [0, 0])  # lang -> [hits, total]
    for _, true, _, _, _, correct in rows:
        per_lang[true][0] += int(correct)
        per_lang[true][1] += 1
    print("\nper-language accuracy:")
    for lang in sorted(per_lang, key=lambda l: per_lang[l][0] / per_lang[l][1]):
        h, tot = per_lang[lang]
        bar = "█" * round(10 * h / tot)
        print(f"  {lang}: {h:>2}/{tot:<2} {100 * h / tot:5.1f}%  {bar}")

    # ── confusion matrix (only rows with any error, to stay readable) ─────────
    langs = sorted(per_lang)
    print("\nconfusion (true → pred), rows with ≥1 miss:")
    print("      " + "".join(f"{l:>4}" for l in langs))
    for true in langs:
        if confusion[true].get(true, 0) == per_lang[true][1]:
            continue  # every clip of this language was correct — skip the row
        cells = "".join(f"{confusion[true].get(p, 0):>4}" for p in langs)
        print(f"  {true:>3} {cells}")

    # ── margin analysis: is confident-and-wrong a problem? ────────────────────
    good = [r[3] for r in rows if r[5]]
    bad = [r[3] for r in rows if not r[5]]
    print("\ntop1−top2 score margin (higher = more confident):")
    print(f"  correct calls: median {statistics.median(good):.3f}" if good else "  correct: none")
    print(f"  wrong   calls: median {statistics.median(bad):.3f}" if bad else "  wrong: none")

    # ── list every miss so we can eyeball patterns ────────────────────────────
    print("\nmisses:")
    for name, true, pred, margin, ms, correct in rows:
        if not correct:
            print(f"  {name:<10} true={true} pred={pred} margin={margin}")


if __name__ == "__main__":
    main()
