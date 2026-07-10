"""
Download a few Google FLEURS test clips per Indian language (with reference
transcripts) → a ground-truthed STT test set. FLEURS is CC-BY, 16 kHz, and each
example carries the gold transcription, so we can compute real WER/CER.

Run:  python download_fleurs.py
"""
import json
import os

import soundfile as sf
from datasets import load_dataset

# FLEURS config → our short language code
LANGS = {"ta_in": "ta", "hi_in": "hi", "te_in": "te", "kn_in": "kn", "ml_in": "ml"}
N_PER_LANG = 2
OUT = "fleurs"
os.makedirs(OUT, exist_ok=True)

refs = {}
for cfg, lc in LANGS.items():
    print(f"— {cfg} …", flush=True)
    try:
        ds = load_dataset("google/fleurs", cfg, split="test", streaming=True)
    except Exception as e:
        print(f"  failed to load {cfg}: {str(e)[:120]}")
        continue
    i = 0
    for ex in ds:
        if i >= N_PER_LANG:
            break
        audio = ex["audio"]
        fn = f"{lc}_{i}.wav"
        sf.write(os.path.join(OUT, fn), audio["array"], audio["sampling_rate"])
        refs[fn] = {"lang": lc, "text": ex["transcription"]}
        print(f"  {fn}: {ex['transcription'][:70]}")
        i += 1

with open(os.path.join(OUT, "references.json"), "w", encoding="utf-8") as f:
    json.dump(refs, f, ensure_ascii=False, indent=2)
print(f"\nSaved {len(refs)} clips + references.json to {OUT}/")
