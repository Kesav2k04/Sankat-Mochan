"""
Speech-to-text for the command post — AI4Bharat IndicConformer-600M (MIT).

Chosen by benchmark (see stt_bench.py / FLEURS): ~6.8% CER and ~500 ms vs
Whisper's ~52% CER / ~40 s on Indian languages. Runs on CPU, so it does NOT
consume the NPU (which stays free for the triage LLM).

The model is loaded ONCE, lazily, on the first transcription (it's a heavy
404-file bundle). Callers pass the language code; if omitted we fall back to
DEFAULT_LANG. (A VoxLingua107 LID front-end for true auto-detect is a planned
add-on — see research notes in the chat / PLAN.md.)
"""
from __future__ import annotations

import os
import threading
import time

# Windows has no unprivileged symlinks, so the HuggingFace cache's default symlink
# strategy fails mid-download with "[WinError 1314] A required privilege is not held
# by the client" — the model never finishes loading and every transcription errors.
# Tell hf_hub to COPY blobs into the snapshot instead (costs a little disk, works
# without Developer Mode / admin). Must be set BEFORE huggingface_hub is imported;
# transformers is imported lazily below, so this module-scope set wins. setdefault
# keeps any explicit override from the environment / .env.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import numpy as np
import soundfile as sf

MODEL_ID = "ai4bharat/indic-conformer-600m-multilingual"
DEFAULT_LANG = "hi"
DEFAULT_MODE = "ctc"  # CTC edged RNNT on WER in our benchmark
SUPPORTED = {
    "hi", "bn", "ta", "te", "kn", "ml", "mr", "gu", "pa", "as", "or", "ur",
}
# Candidates the on-device language-ID sweeps over, most-likely first (ties break
# on this order). All 12 are cheap to score — see identify_language().
LID_CANDIDATES = ["hi", "ur", "bn", "ta", "te", "kn", "ml", "mr", "gu", "pa", "or", "as"]

_model = None
_lock = threading.Lock()


def _ensure_model():
    global _model
    if _model is not None:
        return _model
    with _lock:
        if _model is None:
            from transformers import AutoModel
            _model = AutoModel.from_pretrained(MODEL_ID, trust_remote_code=True)
    return _model


def is_ready() -> bool:
    return _model is not None


def warmup() -> bool:
    """Eagerly load the model (and run one tiny inference to initialize the ONNX
    sessions) so the FIRST real clip doesn't eat the ~13 s cold load. Safe to call
    from a background thread at startup; returns True once the model is hot."""
    try:
        model = _ensure_model()
        import torch
        # 0.5 s of silence @16 kHz — exercises encode + CTC so the sessions are warm.
        try:
            model(torch.zeros(1, 8000, dtype=torch.float32), DEFAULT_LANG, DEFAULT_MODE)
        except Exception:  # noqa: BLE001 — load succeeded; the dummy pass is best-effort
            pass
        return True
    except Exception as e:  # noqa: BLE001 — startup must never crash on a warm-up
        print(f"[stt] warmup failed: {type(e).__name__}: {e}")
        return False


def _ffmpeg_to_wav16k(path_or_bytes) -> bytes | None:
    """Transcode ANY input (browser webm/opus, phone m4a, etc.) → 16 kHz mono WAV
    via ffmpeg. Returns None if ffmpeg isn't available so we can fall back."""
    import shutil
    import subprocess
    if not shutil.which("ffmpeg"):
        return None
    inp = "pipe:0" if isinstance(path_or_bytes, (bytes, bytearray)) else str(path_or_bytes)
    cmd = ["ffmpeg", "-v", "error", "-i", inp, "-ac", "1", "-ar", "16000", "-f", "wav", "pipe:1"]
    stdin = bytes(path_or_bytes) if isinstance(path_or_bytes, (bytes, bytearray)) else None
    proc = subprocess.run(cmd, input=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc.stdout if proc.returncode == 0 and proc.stdout else None


_ffmpeg_present: bool | None = None  # cached availability probe (see transcode_for_web)


def transcode_for_web(data: bytes) -> tuple[bytes, str] | None:
    """Transcode raw mesh audio (AMR-NB in 3GP, which browsers cannot decode) into a
    universally-playable WAV (PCM s16le, mono, 16 kHz). Returns (bytes, content_type) or
    None if ffmpeg is unavailable / the input can't be decoded — callers then keep the raw
    clip and surface a quiet "not playable" status (CLAUDE.md #10), never a crash.

    Security (CLAUDE.md #8): the input is attacker-influenced bytes. We invoke ffmpeg with
    a fixed list-argv (no shell), feed the bytes via pipe:0 / read via pipe:1 (no
    attacker-controlled paths), quiet stderr, and bound wall-clock time so a malformed clip
    cannot hang a worker.
    """
    global _ffmpeg_present
    import shutil
    import subprocess
    if _ffmpeg_present is None:
        _ffmpeg_present = shutil.which("ffmpeg") is not None
    if not _ffmpeg_present or not data:
        return None
    cmd = ["ffmpeg", "-v", "error", "-i", "pipe:0",
           "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-f", "wav", "pipe:1"]
    try:
        proc = subprocess.run(cmd, input=bytes(data), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=15)
    except Exception as exc:  # noqa: BLE001 — transcode failure must degrade, not crash
        print(f"[stt] web transcode failed: {type(exc).__name__}")
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    return proc.stdout, "audio/wav"


def load_audio(path_or_bytes) -> np.ndarray:
    """Return a mono float32 16 kHz waveform from a file path or raw bytes.
    Transcodes via ffmpeg first (handles browser webm/opus + any phone format);
    falls back to reading directly with soundfile for plain wav/flac."""
    import io
    wav_bytes = _ffmpeg_to_wav16k(path_or_bytes)
    if wav_bytes is not None:
        data, _ = sf.read(io.BytesIO(wav_bytes), dtype="float32")
        return np.ascontiguousarray(data if data.ndim == 1 else data.mean(axis=1))

    # Fallback: soundfile can read wav/flac/ogg directly.
    src = io.BytesIO(path_or_bytes) if isinstance(path_or_bytes, (bytes, bytearray)) else path_or_bytes
    data, sr = sf.read(src, dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    if sr != 16000:
        import math
        n_out = int(math.floor(len(data) * 16000 / sr))
        if n_out > 0:
            xp = np.linspace(0.0, 1.0, num=len(data), endpoint=False)
            x = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
            data = np.interp(x, xp, data).astype("float32")
    return np.ascontiguousarray(data)


_lid_cols_cache = None  # {lang: (script_col_tensor, blank_full_col)} — constant, built once


def _lid_cols(model):
    """Per-language full-vocab column indices for language ID, built once and cached.

    model.language_masks[lang] is a BOOLEAN array over the full 5633-token vocab (see
    model_onnx.py: `logprobs[:, :, mask]`). Exactly 257 are True per language — 256
    script tokens + one shared CTC blank. The blank sits at masked-index config.BLANK_ID
    (256) within the selected columns; we split it out so scoring uses script tokens
    only. Languages' 256 script columns are disjoint, which is what makes them separable."""
    global _lid_cols_cache
    if _lid_cols_cache is not None:
        return _lid_cols_cache
    import torch
    cache = {}
    for lang in SUPPORTED:
        true_cols = np.nonzero(np.asarray(model.language_masks[lang], dtype=bool))[0]
        blank_col = int(true_cols[model.config.BLANK_ID])  # masked idx 256 -> full col
        script = torch.tensor([int(c) for c in true_cols if int(c) != blank_col], dtype=torch.long)
        cache[lang] = (script, blank_col)
    _lid_cols_cache = cache
    return cache


def _identify_from_wav(model, wav, candidates: list[str] | None = None) -> dict:
    """Language identification WITHOUT a second model. IndicConformer has no
    auto-detect (indic_stt.py), but its acoustic encoder is language-independent —
    the language only picks a vocab MASK at the CTC decode step (model_onnx.py
    ::_ctc_decode). So we encode once, run the shared CTC head once, then for each
    candidate measure how much probability mass the full-vocab softmax puts on THAT
    language's 256 script tokens over the speech frames. The script the acoustics
    actually match wins. Returns {"lang", "scores"}; degrades to DEFAULT_LANG on API
    drift.

    Method (CTC posterior mass) adapted from the model's own _ctc_decode masking in
    ai4bharat/indic-conformer-600m-multilingual/model_onnx.py (MIT)."""
    import torch
    cands = [c for c in (candidates or LID_CANDIDATES) if c in SUPPORTED]
    try:
        cols = _lid_cols(model)
        enc, _enc_len = model.encode(wav)
        logits = model.models["ctc_decoder"].run(["logprobs"], {"encoder_output": enc})[0]
        logp = torch.from_numpy(logits[0]).log_softmax(dim=-1)  # [T, full_vocab]
        blank = cols[cands[0]][1]
        speech = logp.argmax(dim=-1) != blank              # frames that emitted a real token
        if int(speech.sum()) == 0:
            return {"lang": DEFAULT_LANG, "scores": {}}
        scores: dict[str, float] = {}
        for lang in cands:
            script, _b = cols[lang]
            # log P(token ∈ this language's script | frame), averaged over speech frames.
            frame_mass = torch.logsumexp(logp.index_select(1, script), dim=-1)
            scores[lang] = float(frame_mass[speech].mean())
        best = max(scores, key=scores.get)
        return {"lang": best, "scores": scores}
    except Exception as e:  # noqa: BLE001 — LID must never crash; degrade to default
        print(f"[stt] language id failed, using {DEFAULT_LANG}: {type(e).__name__}: {e}")
        return {"lang": DEFAULT_LANG, "scores": {}}


def identify_language(path_or_bytes, candidates: list[str] | None = None) -> dict:
    """Public language-ID: load audio, encode once, score candidates. See
    _identify_from_wav. Returns {"lang", "scores"}."""
    import torch
    try:
        model = _ensure_model()
        wav = torch.from_numpy(load_audio(path_or_bytes)).unsqueeze(0)
        return _identify_from_wav(model, wav, candidates)
    except Exception as e:  # noqa: BLE001
        print(f"[stt] language id failed, using {DEFAULT_LANG}: {type(e).__name__}: {e}")
        return {"lang": DEFAULT_LANG, "scores": {}}


def transcribe(path_or_bytes, lang: str | None = None, mode: str = DEFAULT_MODE) -> dict:
    """Detect-then-transcribe, mirroring the mobile pipeline: if the caller already
    identified the language (the phone tags each clip with the mesh `ln` field) we
    trust that hint; otherwise we identify the language FROM THE AUDIO first, then
    transcribe with it — because IndicConformer needs the language and blindly
    defaulting to Hindi mistranscribes every other language.

    Returns {text, lang, mode, latency_ms, detected}. Never raises to the caller."""
    import torch
    hint = (lang or "").lower()
    provided = hint in SUPPORTED     # phone already picked a valid language
    detected = False
    try:
        model = _ensure_model()
        wav = torch.from_numpy(load_audio(path_or_bytes)).unsqueeze(0)  # decode once
        t = time.perf_counter()
        if provided:
            use_lang = hint
        else:
            use_lang = _identify_from_wav(model, wav).get("lang", DEFAULT_LANG)
            detected = True
        out = model(wav, use_lang, mode)
        ms = int((time.perf_counter() - t) * 1000)
        text = (out if isinstance(out, str) else str(out)).strip()
        return {"text": text, "lang": use_lang, "mode": mode,
                "latency_ms": ms, "detected": detected}
    except Exception as e:  # noqa: BLE001 — STT must never crash the command post
        print(f"[stt] transcription failed: {e}")
        return {"text": "", "lang": hint or DEFAULT_LANG, "mode": mode,
                "latency_ms": 0, "detected": detected, "error": True}
