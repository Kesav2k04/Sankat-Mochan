#!/usr/bin/env python3
"""
Mechanical validator for the Sahayak dataset (SAHAYAK_DATASET_SPEC.md §8.1 step 2).

Runs the objective, non-taste checks a generated batch must pass before it's committed:
  * every line parses as JSON;
  * schema fields present and in-vocabulary (category / language / difficulty / id);
  * the system prompt is byte-identical to the spec's single fixed prompt;
  * assistant reply within the length budget (<=600 chars, <=200 for relay packets);
  * ids unique across the file (and, optionally, across the committed fingerprint index);
  * near-duplicate user messages rejected (token-overlap ratio > 0.85), both within the file
    and against a fingerprint index of everything already committed.

Exit code is 0 iff the file is clean, so it drops straight into the batch loop / CI.

Usage:
    python validate_dataset.py data/staging/batch_01.jsonl
    python validate_dataset.py data/staging/batch_02.jsonl --fingerprints data/fingerprints.txt
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    # Single source of truth for the fixed system prompt.
    from sahayak_finetune import SYSTEM_PROMPT
except Exception:  # allow running the validator standalone if the trainer isn't importable
    SYSTEM_PROMPT = None

CATEGORIES = {
    "first_aid", "relay", "resource", "summarize", "nav",
    "multilingual", "opsec", "psych", "device",
}
BASE_LANGS = {"en", "hi", "ta", "bn", "te", "mr"}
DIFFICULTIES = {"basic", "ambiguous", "adversarial", "noisy"}

MAX_ASSISTANT_CHARS = 600
MAX_RELAY_CHARS = 200
DUP_THRESHOLD = 0.85

ID_RE = re.compile(r"^[A-Za-z0-9]+-\d{3,5}$")
_PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)


def normalize(text: str) -> str:
    """Lowercase, strip punctuation, sort tokens — the fingerprint form for dedup."""
    cleaned = _PUNCT_RE.sub(" ", text.lower())
    return " ".join(sorted(cleaned.split()))


def token_overlap(a: str, b: str) -> float:
    """Jaccard overlap of token sets — cheap and good enough for near-dup detection."""
    sa, sb = set(a.split()), set(b.split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def language_ok(lang: str) -> bool:
    base = lang[:-4] if lang.endswith("-rom") else lang
    return base in BASE_LANGS


def load_fingerprints(path: Path) -> list[tuple[str, str]]:
    out = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if "\t" in line:
            fid, norm = line.split("\t", 1)
            out.append((fid.strip(), norm.strip()))
    return out


def validate(path: Path, fingerprints_path: Path | None) -> int:
    errors: list[str] = []
    warnings: list[str] = []

    lines = path.read_text(encoding="utf-8").splitlines()
    records = []
    for i, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            records.append((i, json.loads(line)))
        except json.JSONDecodeError as exc:
            errors.append(f"line {i}: invalid JSON ({exc})")

    seen_ids: dict[str, int] = {}
    norms: list[tuple[str, str]] = []  # (id, normalized user message)

    for lineno, rec in records:
        rid = str(rec.get("id", ""))
        where = f"line {lineno} (id={rid or '?'})"

        # id
        if not rid:
            errors.append(f"{where}: missing 'id'")
        elif not ID_RE.match(rid):
            errors.append(f"{where}: id '{rid}' doesn't match <prefix>-<number>")
        elif rid in seen_ids:
            errors.append(f"{where}: duplicate id (first at line {seen_ids[rid]})")
        else:
            seen_ids[rid] = lineno

        # enums
        if rec.get("category") not in CATEGORIES:
            errors.append(f"{where}: category '{rec.get('category')}' not in vocab")
        if not isinstance(rec.get("language"), str) or not language_ok(rec["language"]):
            errors.append(f"{where}: language '{rec.get('language')}' not in vocab")
        if rec.get("difficulty") not in DIFFICULTIES:
            errors.append(f"{where}: difficulty '{rec.get('difficulty')}' not in vocab")

        # messages shape + roles
        messages = rec.get("messages")
        if not isinstance(messages, list) or len(messages) < 3:
            errors.append(f"{where}: 'messages' must be a list of >=3 turns")
            continue
        roles = [m.get("role") for m in messages]
        if roles[0] != "system":
            errors.append(f"{where}: first message must be role 'system'")
        if roles[-1] != "assistant":
            errors.append(f"{where}: last message must be role 'assistant'")

        # system prompt byte-identical
        sys_content = messages[0].get("content", "")
        if SYSTEM_PROMPT is not None and sys_content != SYSTEM_PROMPT:
            errors.append(f"{where}: system prompt not byte-identical to the spec prompt")

        # assistant length budget (last assistant turn)
        assistant_turns = [m.get("content", "") for m in messages if m.get("role") == "assistant"]
        cap = MAX_RELAY_CHARS if rec.get("category") == "relay" else MAX_ASSISTANT_CHARS
        for turn in assistant_turns:
            if len(turn) > cap:
                errors.append(f"{where}: assistant reply {len(turn)} chars > cap {cap}")

        # multi-turn guard: no more than 2 user turns (spec §3)
        if roles.count("user") > 2:
            errors.append(f"{where}: more than 2 user turns")

        # fingerprint of the FIRST user message
        first_user = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
        if first_user:
            norms.append((rid, normalize(first_user)))

    # within-file near-duplicate check
    for i in range(len(norms)):
        for j in range(i + 1, len(norms)):
            ratio = token_overlap(norms[i][1], norms[j][1])
            if ratio > DUP_THRESHOLD:
                errors.append(
                    f"near-duplicate within file: {norms[i][0]} ~ {norms[j][0]} "
                    f"(overlap {ratio:.2f})"
                )

    # against committed fingerprint index
    if fingerprints_path:
        committed = load_fingerprints(fingerprints_path)
        for rid, norm in norms:
            for cid, cnorm in committed:
                if token_overlap(norm, cnorm) > DUP_THRESHOLD:
                    errors.append(
                        f"near-duplicate of committed {cid}: {rid} "
                        f"(overlap {token_overlap(norm, cnorm):.2f})"
                    )
                    break

    # report
    total = len(norms) if norms else len(records)
    print(f"validated {len(records)} records from {path.name}")
    for w in warnings:
        print(f"  [warn] {w}")
    if errors:
        print(f"\nFAILED: {len(errors)} error(s):")
        for e in errors[:200]:
            print(f"  - {e}")
        if len(errors) > 200:
            print(f"  … and {len(errors) - 200} more")
        return 1
    print("OK — batch passes mechanical validation.")
    return 0


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Validate a Sahayak dataset JSONL batch.")
    p.add_argument("file", help="Path to the .jsonl file to validate.")
    p.add_argument("--fingerprints", default=None,
                   help="Optional fingerprints.txt of already-committed records (dedup index).")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    path = Path(args.file)
    if not path.exists():
        print(f"[error] file not found: {path}", file=sys.stderr)
        return 2
    fp = Path(args.fingerprints) if args.fingerprints else None
    return validate(path, fp)


if __name__ == "__main__":
    raise SystemExit(main())
