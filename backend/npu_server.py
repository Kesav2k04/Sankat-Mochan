"""
NPU model server — the OpenAI-compatible shim around onnxruntime-genai (QNN).

Runs on the AI PC (Snapdragon X Elite, Windows-on-ARM). It loads an
onnxruntime-genai model folder that was built for the QNN / Hexagon NPU (the
artifact AI Hub / the genai builder produces) and exposes the SAME
`/v1/chat/completions` endpoint the popular tools use. So the command post
(app.py / triage.py) points at it with ONE env line — no code change:

    LLM_BASE_URL=http://localhost:8010/v1

Fallback ladder is just a different URL: GenieX / AnythingLLM / LM Studio all
speak this same protocol.

Run on the X Elite (inside an ARM64 Python venv):
    pip install onnxruntime-genai            # or the QNN build: onnxruntime-genai-qnn
    NPU_MODEL_DIR=C:\\models\\qwen3-4b-qnn  uvicorn npu_server:app --port 8010

NOTE: this file is written on the Mac but TARGETS the X Elite — it can't run
here (no onnxruntime-genai / no NPU). The generation loop follows the current
onnxruntime-genai API; verify against the installed version on the device (the
append_tokens / generate_next_token names are the version-sensitive spot).
"""
from __future__ import annotations

import os
import time
import uuid
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

MODEL_DIR = os.getenv("NPU_MODEL_DIR", "")
DEFAULT_MAX_TOKENS = int(os.getenv("NPU_MAX_TOKENS", "256"))

app = FastAPI(title="Sankat-Mochan NPU server (onnxruntime-genai / QNN)")

# Lazy import so the file at least loads for inspection without the package.
try:
    import onnxruntime_genai as og
except Exception:  # pragma: no cover - only true off-device
    og = None

_model: Any = None
_tokenizer: Any = None


def _ensure_loaded() -> str | None:
    """Load the model once. Returns an error string, or None on success."""
    global _model, _tokenizer
    if _model is not None:
        return None
    if og is None:
        return "onnxruntime-genai is not installed (install it on the X Elite / QNN build)"
    if not MODEL_DIR or not os.path.isdir(MODEL_DIR):
        return f"NPU_MODEL_DIR not set or not a directory: {MODEL_DIR!r}"
    _model = og.Model(MODEL_DIR)        # provider (QNN/NPU) is baked into the model's genai_config.json
    _tokenizer = og.Tokenizer(_model)
    return None


def _build_prompt(messages: list[dict[str, str]]) -> str:
    """Render chat messages to a prompt. Prefer the model's chat template;
    fall back to a generic system/user/assistant layout."""
    try:
        # Newer onnxruntime-genai exposes a chat-template helper.
        return _tokenizer.apply_chat_template(
            messages=messages, add_generation_prompt=True
        )
    except Exception:
        parts = []
        for m in messages:
            role, content = m.get("role", "user"), m.get("content", "")
            parts.append(f"<|{role}|>\n{content}")
        parts.append("<|assistant|>\n")
        return "\n".join(parts)


def _generate(prompt: str, max_tokens: int, temperature: float) -> tuple[str, int, int]:
    """Run one non-streaming generation. Returns (text, prompt_tokens, completion_tokens)."""
    input_tokens = _tokenizer.encode(prompt)
    params = og.GeneratorParams(_model)
    params.set_search_options(
        max_length=len(input_tokens) + max_tokens,
        temperature=max(0.0, temperature),
        do_sample=temperature > 0.0,
    )
    generator = og.Generator(_model, params)
    # --- version-sensitive block (verify on device) ---
    generator.append_tokens(input_tokens)
    produced: list[int] = []
    while not generator.is_done():
        generator.generate_next_token()
        seq = generator.get_sequence(0)
        if len(seq) > len(input_tokens) + len(produced):
            produced.append(int(seq[-1]))
    # ---------------------------------------------------
    text = _tokenizer.decode(produced).strip()
    return text, len(input_tokens), len(produced)


@app.get("/v1/models")
async def models() -> dict[str, Any]:
    name = os.path.basename(MODEL_DIR.rstrip("/\\")) or "npu-model"
    return {"object": "list", "data": [{"id": name, "object": "model", "owned_by": "local-npu"}]}


@app.get("/health")
async def health() -> dict[str, Any]:
    err = _ensure_loaded()
    return {"ok": err is None, "model_dir": MODEL_DIR, "error": err}


@app.post("/v1/chat/completions")
async def chat_completions(body: dict[str, Any]) -> JSONResponse:
    err = _ensure_loaded()
    if err:
        # Rule #10: generic status to callers; detail stays in the server log.
        print(f"[npu] not ready: {err}")
        return JSONResponse({"error": {"message": err, "type": "model_not_ready"}}, status_code=503)

    messages = body.get("messages", [])
    max_tokens = int(body.get("max_tokens", DEFAULT_MAX_TOKENS))
    temperature = float(body.get("temperature", 0.1))

    prompt = _build_prompt(messages)
    started = time.perf_counter()
    try:
        text, p_tok, c_tok = _generate(prompt, max_tokens, temperature)
    except Exception as e:
        print(f"[npu] generation failed: {e}")
        return JSONResponse({"error": {"message": "generation failed", "type": "inference_error"}}, status_code=500)
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    return JSONResponse(
        {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body.get("model", os.path.basename(MODEL_DIR) or "npu-model"),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": p_tok,
                "completion_tokens": c_tok,
                "total_tokens": p_tok + c_tok,
            },
            # handy for the deck's NPU-vs-CPU latency slide:
            "x_latency_ms": elapsed_ms,
            "x_tokens_per_s": round(c_tok / (elapsed_ms / 1000), 1) if elapsed_ms else None,
        }
    )
