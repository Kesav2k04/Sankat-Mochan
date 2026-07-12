"""
Backend benchmark — run the SAME triage task against every OpenAI-compatible
backend you have running (vLLM, LM Studio, Ollama, llama.cpp) and rank them by
latency + throughput, so we pick the fastest objectively.

1. Start each backend's server with a model loaded (any port).
2. List them in backends.json (see backends.example.json), or use --url/--model.
3. Run:  python bench.py           (uses backends.json)
         python bench.py --url http://localhost:1234/v1 --model qwen2.5-3b-instruct

Nothing here changes the app — it just probes endpoints.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path
from typing import Any

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ modules

import triage
from models import parse_envelope, sample_sos

ROUNDS = 4  # SOS samples per backend (one of each language/scenario)


async def probe(name: str, url: str, model: str) -> dict[str, Any]:
    lats: list[int] = []
    toks: list[float] = []
    ok = 0
    good_json = 0
    outputs: list[dict[str, Any]] = []  # captured translations for quality eyeballing
    for i in range(ROUNDS):
        env = parse_envelope(sample_sos(i))
        t0 = time.perf_counter()
        res = await triage.triage(env, base_url=url, model=model)
        dt = (time.perf_counter() - t0) * 1000
        if res.get("ai"):
            ok += 1
            lats.append(res.get("latency_ms") or int(dt))
            ct = res.get("completion_tokens")
            if ct and res.get("latency_ms"):
                toks.append(ct / (res["latency_ms"] / 1000))
            if res.get("english") and res.get("category"):
                good_json += 1
        outputs.append({
            "lang": env.get("lang"),
            "src": env.get("gist"),
            "english": res.get("english", ""),
            "urgency": res.get("urgency"),
            "category": res.get("category"),
            "ai": res.get("ai", False),
        })
    return {
        "name": name,
        "url": url,
        "model": model,
        "ok": ok,
        "rounds": ROUNDS,
        "good_json": good_json,
        "avg_ms": round(statistics.mean(lats)) if lats else None,
        "p50_ms": round(statistics.median(lats)) if lats else None,
        "tok_s": round(statistics.mean(toks), 1) if toks else None,
        "outputs": outputs,
    }


def load_backends(args: argparse.Namespace) -> list[dict[str, str]]:
    if args.url:
        return [{"name": args.name or "cli", "url": args.url, "model": args.model or "default"}]
    cfg = Path(__file__).parents[1] / "backends.json"
    if cfg.exists():
        return json.loads(cfg.read_text())
    # Sensible defaults for the common local servers.
    return [
        {"name": "lmstudio", "url": "http://localhost:1234/v1", "model": "qwen2.5-3b-instruct"},
        {"name": "ollama", "url": "http://localhost:11434/v1", "model": "qwen2.5:3b"},
        {"name": "vllm", "url": "http://localhost:8000/v1", "model": "Qwen/Qwen2.5-3B-Instruct"},
        {"name": "llamacpp", "url": "http://localhost:8080/v1", "model": "qwen2.5-3b"},
    ]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url"); ap.add_argument("--model"); ap.add_argument("--name")
    args = ap.parse_args()
    backends = load_backends(args)

    print(f"Benchmarking {len(backends)} backend(s), {ROUNDS} SOS each…\n")
    results = []
    for b in backends:
        print(f"  → {b['name']} ({b['url']}, {b['model']}) …", flush=True)
        results.append(await probe(b["name"], b["url"], b["model"]))

    live = [r for r in results if r["ok"] > 0]
    live.sort(key=lambda r: (r["avg_ms"] is None, r["avg_ms"] or 1e9))

    print("\n" + "=" * 78)
    print(f"{'backend':<12}{'ok':>6}{'good':>6}{'avg ms':>10}{'p50 ms':>10}{'tok/s':>10}   model")
    print("-" * 78)
    for r in results:
        avg = r["avg_ms"] if r["avg_ms"] is not None else "—"
        p50 = r["p50_ms"] if r["p50_ms"] is not None else "—"
        ts = r["tok_s"] if r["tok_s"] is not None else "—"
        print(f"{r['name']:<12}{r['ok']:>3}/{r['rounds']:<2}{r['good_json']:>6}{str(avg):>10}{str(p50):>10}{str(ts):>10}   {r['model']}")
    print("=" * 78)
    if live:
        w = live[0]
        print(f"\n🏆 fastest: {w['name']}  ({w['avg_ms']} ms avg, {w['tok_s']} tok/s)")
        print(f"   → set in .env:  LLM_BASE_URL={w['url']}   LLM_MODEL={w['model']}")
    else:
        print("\nNo backend responded. Start a server (LM Studio / Ollama / vLLM) and retry.")

    # Quality view — eyeball the actual translations (speed means nothing if the
    # Tamil/Hindi translation is wrong). This is chip-independent → picks the model.
    print("\n" + "=" * 78)
    print("TRANSLATION QUALITY (judge these by hand — same on Mac and NPU)")
    for r in results:
        if not r["ok"]:
            continue
        print(f"\n── {r['name']} ({r['model']}) ─────────────────────────────")
        for o in r["outputs"]:
            print(f"  [{o['lang']}] {o['src']}")
            print(f"     → u{o['urgency']} · {o['category']} · \"{o['english']}\"")
    print("=" * 78)


if __name__ == "__main__":
    asyncio.run(main())
