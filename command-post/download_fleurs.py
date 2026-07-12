"""
Download Google FLEURS test clips (with reference transcripts) → a ground-truthed
STT/LID test set covering all 12 languages stt.py's language-ID sweeps over.

FLEURS is CC-BY, 16 kHz, gold transcriptions → real WER/CER + a real LID
confusion matrix.

Why this is written the awkward way: FLEURS's HF parquet stores each language's
whole test split as ONE ~200-900 MB row group with no page index, so neither
streaming, the datasets-server rows API, nor parquet range-reads can slice it —
they all try to pull the entire row group and blow the 300 MB scan limit / RAM.
The only robust option is to download each test shard fully (resumable via
hf_hub_download), extract N rows, then DELETE the shard before moving on so peak
disk stays ~one shard, not 7 GB. Reading the whole shard costs the same whether
we keep 10 rows or 50, so we keep a lot — a richer baseline for free.

Run:  python download_fleurs.py            # 40 clips/lang
      python download_fleurs.py 20
"""
import io
import json
import os
import sys

import pyarrow.parquet as pq
import soundfile as sf
from huggingface_hub import hf_hub_download

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# FLEURS config → our short code. Verified via get_dataset_config_names; don't guess.
LANGS = {
    "hi_in": "hi", "ur_pk": "ur", "bn_in": "bn", "ta_in": "ta",
    "te_in": "te", "kn_in": "kn", "ml_in": "ml", "mr_in": "mr",
    "gu_in": "gu", "pa_in": "pa", "or_in": "or", "as_in": "as",
}
N_PER_LANG = int(sys.argv[1]) if len(sys.argv) > 1 else 40
OUT = "fleurs"
# Per-PID temp dir: if two copies of this script ever run at once they must NOT share a
# shard staging dir, or each os.remove() below deletes the other's in-flight download and
# both loop forever extracting nothing (observed 2026-07-12). Isolating the dir per process
# keeps concurrent runs from corrupting each other; both still write identical wavs to OUT/.
SHARD_TMP = os.path.join(OUT, f"_shard_tmp_{os.getpid()}")
os.makedirs(OUT, exist_ok=True)

refs = {}
for cfg, lc in LANGS.items():
    print(f"— {cfg} ({lc}) …", flush=True)
    shard_path = None
    try:
        # Resumable full-shard download to a temp dir we control (so we can delete it).
        shard_path = hf_hub_download(
            "google/fleurs", f"{cfg}/test/0000.parquet",
            repo_type="dataset", revision="refs/convert/parquet",
            local_dir=SHARD_TMP,
        )
        # Read only the columns we need, first N rows, from the single row group.
        tbl = pq.ParquetFile(shard_path).read_row_group(
            0, columns=["audio", "transcription"]
        ).slice(0, N_PER_LANG)
        # FLEURS nests audio as a struct column: audio: struct<bytes, path> — it used to
        # be a top-level "bytes" column. Verified via schema_arrow on the HF parquet
        # (refs/convert/parquet) on 2026-07-12; reading "bytes" now KeyErrors per language.
        audio_rows = tbl.column("audio").to_pylist()  # [{"bytes":…, "path":…}, …]
        texts = tbl.column("transcription").to_pylist()
        for i, (a, txt) in enumerate(zip(audio_rows, texts)):
            data, sr = sf.read(io.BytesIO(a["bytes"]), dtype="float32")
            fn = f"{lc}_{i}.wav"
            sf.write(os.path.join(OUT, fn), data, sr)
            refs[fn] = {"lang": lc, "text": txt}
        print(f"  saved {len(audio_rows)} clips")
    except Exception as e:  # network / config drift: skip this lang, keep the rest
        print(f"  FAILED {cfg}: {type(e).__name__}: {str(e)[:140]}")
    finally:
        if shard_path and os.path.exists(shard_path):
            os.remove(shard_path)  # reclaim disk before the next (bigger) shard

# Clean up the temp shard dir tree.
try:
    import shutil
    shutil.rmtree(SHARD_TMP, ignore_errors=True)
except Exception:
    pass

with open(os.path.join(OUT, "references.json"), "w", encoding="utf-8") as f:
    json.dump(refs, f, ensure_ascii=False, indent=2)
by_lang = {}
for r in refs.values():
    by_lang[r["lang"]] = by_lang.get(r["lang"], 0) + 1
print(f"\nSaved {len(refs)} clips + references.json to {OUT}/")
print("per language:", dict(sorted(by_lang.items())))
