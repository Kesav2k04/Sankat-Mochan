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

import threading
import time

import numpy as np
import soundfile as sf

MODEL_ID = "ai4bharat/indic-conformer-600m-multilingual"
DEFAULT_LANG = "hi"
DEFAULT_MODE = "ctc"  # CTC edged RNNT on WER in our benchmark
SUPPORTED = {
    "hi", "bn", "ta", "te", "kn", "ml", "mr", "gu", "pa", "as", "or", "ur",
}

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


def transcribe(path_or_bytes, lang: str | None = None, mode: str = DEFAULT_MODE) -> dict:
    """Transcribe audio → {text, lang, mode, latency_ms}. Never raises to the caller."""
    import torch
    lang = (lang or DEFAULT_LANG).lower()
    if lang not in SUPPORTED:
        lang = DEFAULT_LANG
    try:
        model = _ensure_model()
        wav = torch.from_numpy(load_audio(path_or_bytes)).unsqueeze(0)
        t = time.perf_counter()
        out = model(wav, lang, mode)
        ms = int((time.perf_counter() - t) * 1000)
        text = (out if isinstance(out, str) else str(out)).strip()
        return {"text": text, "lang": lang, "mode": mode, "latency_ms": ms}
    except Exception as e:  # noqa: BLE001 — STT must never crash the command post
        print(f"[stt] transcription failed: {e}")
        return {"text": "", "lang": lang, "mode": mode, "latency_ms": 0, "error": True}
