"""
Envelope validation — mirrors CONTRACT 1 in the Pi HANDOFF.md and the Android
SosMessage.kt. All incoming mesh data is UNTRUSTED (project rule #8): validate
size, type, and ranges; never trust or execute the contents.
"""
from __future__ import annotations

import json
from typing import Any

# 244 B is the LoRa/BLE WIRE cap (enforced when the phone ENCODES). On INGEST we
# validate more leniently: native-script Indic is ~3 bytes/char, and the command
# post may also receive richer envelopes over LAN (not just LoRa). Still bounded
# so untrusted input can't be huge (rule #8).
WIRE_MAX_BYTES = 244
PARSE_MAX_BYTES = 4096
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
        if len(raw) > PARSE_MAX_BYTES:
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
    """Demo scenario envelopes for the inject button — exercises the full
    intelligence pipeline: 3 reports + 1 sensor cluster at the bridge
    (corroboration), a lone medical, a trapped pair, and a no-GPS case.
    Native-script Indic — what on-device STT actually emits."""
    #  lang, text, category, urgency, lat, lng, origin, locationHint
    samples = [
        # cluster A: Chooralmala bridge flood — 3 humans within ~80m + sensor
        ("ta", "தண்ணீர் வேகமாக ஏறுகிறது, இங்கே குழந்தைகள் இருக்கிறார்கள்", "flood", 5, 11.6854, 76.1320, "ph-01", "Chooralmala bridge"),
        ("ml", "ഞങ്ങൾ പാലത്തിനടുത്താണ്, വെള്ളം കയറിക്കൊണ്ടിരിക്കുന്നു", "flood", 4, 11.6858, 76.1326, "ph-02", "Chooralmala bridge"),
        ("sensor", "WLS-1 water level 2.4m and rising 12cm/min", "sensor", 4, 11.6851, 76.1317, "unoq-1", "Chooralmala bridge"),
        ("hi", "पुल के नीचे दो परिवार फंसे हुए हैं, जल्दी आइए", "flood", 5, 11.6849, 76.1324, "ph-03", "Chooralmala bridge"),
        # lone incidents
        ("hi", "मेरी माँ को साँस लेने में तकलीफ़ हो रही है, दवाई चाहिए", "medical", 4, 11.6921, 76.1258, "ph-04", "Attamala"),
        ("ta", "சுவர் இடிஞ்சு விழுந்துச்சு, ரெண்டு பேர் உள்ளே மாட்டிக்கிட்டாங்க", "trapped", 5, 11.6790, 76.1385, "ph-05", "Mundakkai"),
        # no-GPS lane — still triaged + dispatchable, not map-pinned
        ("ta", "பழைய கோவில் பக்கத்துல மாட்டிக்கிட்டேன், GPS வரலை", "trapped", 4, None, None, "ph-06", "old church"),
        ("en", "Eight estate workers stranded up the hill above the school", "flood", 3, 11.6712, 76.1443, "ph-07", "Vellarimala"),
    ]
    lang, gist, cat, urg, la, lo, origin, hint = samples[seq % len(samples)]
    env: dict[str, Any] = {
        "i": f"test-{seq}", "t": "SOS", "o": origin, "u": urg, "c": cat,
        "l": hint, "g": gist, "ln": lang, "ts": 0, "h": (seq % 4) + 1,
    }
    if la is not None:
        env["la"], env["lo"] = la, lo
    return env
