"""
Envelope validation — mirrors CONTRACT 1 in the Pi HANDOFF.md and the Android
SosMessage.kt. All incoming mesh data is UNTRUSTED (project rule #8): validate
size, type, and ranges; never trust or execute the contents.
"""
from __future__ import annotations

import json
from typing import Any

MAX_BYTES = 260  # small slack over the 244 the radios enforce
VALID_TYPES = {"SOS", "DELIVERED", "ACCEPTED"}


class InvalidEnvelope(ValueError):
    """Raised when an incoming payload fails validation — caller drops it."""


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _coord(o: dict, key: str, lo: float, hi: float) -> float | None:
    if key not in o:
        return None
    try:
        v = float(o[key])
    except (TypeError, ValueError):
        return None
    if v != v or v in (float("inf"), float("-inf")):  # NaN / inf
        return None
    return v if lo <= v <= hi else None


def parse_envelope(raw: bytes | str | dict) -> dict[str, Any]:
    """Parse + validate one envelope. Returns a normalized dict or raises
    InvalidEnvelope. Short-key wire format decoded into readable field names."""
    if isinstance(raw, (bytes, bytearray)):
        if len(raw) > MAX_BYTES:
            raise InvalidEnvelope("oversized payload")
        raw = raw.decode("utf-8", errors="strict")
    if isinstance(raw, str):
        try:
            o = json.loads(raw)
        except json.JSONDecodeError as e:
            raise InvalidEnvelope(f"bad json: {e}") from e
    elif isinstance(raw, dict):
        o = raw
    else:
        raise InvalidEnvelope("unsupported payload type")

    if not isinstance(o, dict):
        raise InvalidEnvelope("payload is not an object")

    msg_id = str(o.get("i", ""))[:32]
    origin = str(o.get("o", ""))[:32]
    mtype = str(o.get("t", ""))
    if not msg_id or not origin:
        raise InvalidEnvelope("missing id/origin")
    if mtype not in VALID_TYPES:
        raise InvalidEnvelope(f"bad type: {mtype!r}")

    try:
        urgency = int(_clamp(int(o.get("u", 3)), 1, 5))
    except (TypeError, ValueError):
        urgency = 3
    try:
        hops = int(_clamp(int(o.get("h", 0)), 0, 15))
    except (TypeError, ValueError):
        hops = 0

    return {
        "id": msg_id,
        "type": mtype,
        "origin": origin,
        "refId": (str(o["r"])[:32] if "r" in o else None),
        "urgency": urgency,
        "category": str(o.get("c", ""))[:48],
        "locationHint": str(o.get("l", ""))[:64],
        "gist": str(o.get("g", ""))[:200],
        "lang": str(o.get("ln", "en"))[:8],
        "lat": _coord(o, "la", -90.0, 90.0),
        "lng": _coord(o, "lo", -180.0, 180.0),
        "ts": int(o.get("ts", 0)) if str(o.get("ts", "0")).lstrip("-").isdigit() else 0,
        "hops": hops,
    }


def sample_sos(seq: int = 0) -> dict[str, Any]:
    """A realistic test envelope for the inject button / benchmark."""
    samples = [
        ("ta", "Veedu moodhi irukku, thanni varudhu — kaappaathunga", "trapped", 5, 11.6854, 76.1320),
        ("hi", "Meri maa ko saans lene mein takleef ho rahi hai, dawai chahiye", "medical", 4, 11.6871, 76.1298),
        ("ta", "Sagathi adaipattadhu, rendu per ullea maatti irukkaanga", "trapped", 5, 11.6840, 76.1355),
        ("en", "Water rising fast near the old bridge, need a boat", "flood", 3, 11.6889, 76.1301),
    ]
    lang, gist, cat, urg, la, lo = samples[seq % len(samples)]
    return {
        "i": f"test-{seq}", "t": "SOS", "o": "test", "u": urg, "c": cat,
        "l": "Sector 4", "g": gist, "ln": lang, "la": la, "lo": lo,
        "ts": 0, "h": 1,
    }
