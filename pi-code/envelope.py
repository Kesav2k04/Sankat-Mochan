"""
CONTRACT 1 — the SOS envelope, identical on both mesh tiers.

This is a faithful port of the Android side (`model/SosMessage.kt`), which is the
source of truth. The wire format is compact small-key JSON, UTF-8, <= 244 bytes so
one envelope fits a single BLE write at a 247-byte MTU AND a 255-byte LoRa frame.

Every envelope arriving from BLE or LoRa is UNTRUSTED (CLAUDE.md #8): we validate
size, type and field ranges before touching it, cap string lengths, and never
interpret any field as a command. `decode()` returning None means "drop it".
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Any, Dict, Optional

MAX_BYTES = 244          # ATT payload budget at a 247-byte MTU (247 - 3 ATT header)
DECODE_TOLERANCE = 8     # mirrors the Kotlin side's small slack on inbound size
MAX_ID = 32
MAX_TEXT = 200
MAX_HOPS = 15

TYPES = ("SOS", "DELIVERED", "ACCEPTED")


@dataclass(frozen=True)
class Envelope:
    id: str
    type: str
    origin: str
    ref_id: Optional[str] = None
    urgency: int = 3
    category: str = ""
    location_hint: str = ""
    gist: str = ""
    lang: str = "en"
    lat: Optional[float] = None
    lng: Optional[float] = None
    ts: int = 0
    hops: int = 0

    @property
    def has_location(self) -> bool:
        return self.lat is not None and self.lng is not None

    def bumped(self) -> "Envelope":
        """The same envelope one hop further along, clamped like the phone does."""
        return replace(self, hops=min(self.hops + 1, MAX_HOPS))

    def to_dict(self) -> Dict[str, Any]:
        o: Dict[str, Any] = {"i": self.id, "t": self.type, "o": self.origin}
        if self.ref_id is not None:
            o["r"] = self.ref_id
        o["u"] = self.urgency
        o["c"] = self.category
        o["l"] = self.location_hint
        o["g"] = self.gist
        o["ln"] = self.lang
        if self.lat is not None and self.lng is not None:
            o["la"] = self.lat
            o["lo"] = self.lng
        o["ts"] = self.ts
        o["h"] = self.hops
        return o

    def _raw(self, gist: str) -> bytes:
        return json.dumps(replace(self, gist=gist).to_dict(),
                          separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    def encode(self) -> bytes:
        """UTF-8 JSON, <= MAX_BYTES. Only the free-text gist is trimmed to fit.

        Trims one CHARACTER at a time. The Kotlin original drops a *byte* count from a
        *character* string (`dropLast(bytes.size - MAX_BYTES)`), which throws away the
        whole gist for Tamil/Hindi text where one character is three UTF-8 bytes — and
        those are exactly the languages this app exists to carry. Both produce a valid
        <= 244-byte envelope, so the wire contract is unchanged; this one just keeps as
        much of the victim's message as physically fits.
        """
        gist = self.gist
        raw = self._raw(gist)
        while len(raw) > MAX_BYTES and gist:
            gist = gist[:-1]
            raw = self._raw(gist)
        return raw


def _clamp_str(value: Any, limit: int) -> str:
    return value[:limit] if isinstance(value, str) else ""


def _coord(o: Dict[str, Any], key: str, lo: float, hi: float) -> Optional[float]:
    if key not in o:
        return None
    v = o[key]
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return None
    v = float(v)
    # NaN/inf survive json.loads via the non-standard literals; reject them.
    if v != v or v in (float("inf"), float("-inf")) or not lo <= v <= hi:
        return None
    return v


def _clamp_int(o: Dict[str, Any], key: str, default: int, lo: int, hi: int) -> int:
    v = o.get(key, default)
    if isinstance(v, bool) or not isinstance(v, int):
        return default
    return max(lo, min(hi, v))


def decode(raw: bytes) -> Optional[Envelope]:
    """Parse + validate. Returns None for anything we should drop on the floor."""
    if not raw or len(raw) > MAX_BYTES + DECODE_TOLERANCE:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    try:
        o = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(o, dict):
        return None

    msg_id = _clamp_str(o.get("i"), MAX_ID)
    origin = _clamp_str(o.get("o"), MAX_ID)
    msg_type = o.get("t")
    if not msg_id or not origin or msg_type not in TYPES:
        return None

    ts = o.get("ts", 0)
    if isinstance(ts, bool) or not isinstance(ts, int) or ts < 0:
        ts = 0

    return Envelope(
        id=msg_id,
        type=msg_type,
        origin=origin,
        ref_id=_clamp_str(o["r"], MAX_ID) if "r" in o else None,
        urgency=_clamp_int(o, "u", 3, 1, 5),
        category=_clamp_str(o.get("c"), 48),
        location_hint=_clamp_str(o.get("l"), 64),
        gist=_clamp_str(o.get("g"), MAX_TEXT),
        lang=_clamp_str(o.get("ln"), 8) or "en",
        lat=_coord(o, "la", -90.0, 90.0),
        lng=_coord(o, "lo", -180.0, 180.0),
        ts=ts,
        hops=_clamp_int(o, "h", 0, 0, MAX_HOPS),
    )


def digest(raw: bytes) -> str:
    """Short content hash. Logged at TX and again at RX so a reader can confirm the
    exact bytes crossed the air rather than being reconstructed locally."""
    return hashlib.sha256(raw).hexdigest()[:12]


# --- Rendering untrusted envelopes into a log line --------------------------

URGENCY_WORDS = {1: "lowest", 2: "low", 3: "normal", 4: "high", 5: "life-threatening"}

# Control characters, including newline and carriage return.
_CTRL = {c: None for c in range(0x20)}
_CTRL[0x7F] = None


def preview(text: str, limit: int = 60) -> str:
    """One-line, length-capped rendering of untrusted free text (CLAUDE.md #8).

    Control characters are stripped, not escaped: a gist arriving off the air that
    contained "\\n02:09:13 INFO sankat: probe OK" would otherwise forge a log line.
    """
    if not isinstance(text, str) or not text:
        return ""
    clean = text.translate(_CTRL).strip()
    if len(clean) > limit:
        clean = clean[: limit - 1] + "…"
    return clean


def describe(msg: Envelope) -> str:
    """`SOS c363-0 from phone c363, urgency 4/5 (high), near Block C stairwell`."""
    bits = [f"{msg.type} {msg.id}", f"from phone {msg.origin}"]
    if msg.type == "SOS":
        bits.append(f"urgency {msg.urgency}/5 ({URGENCY_WORDS.get(msg.urgency, '?')})")
    if msg.category:
        bits.append(preview(msg.category, 24))
    if msg.location_hint:
        bits.append(f"near {preview(msg.location_hint, 32)}")
    if msg.has_location:
        bits.append(f"at {msg.lat:.5f},{msg.lng:.5f}")
    return ", ".join(bits)


def message_text(msg: Envelope) -> str:
    """The words the victim actually typed, ready to sit on its own log line."""
    body = preview(msg.gist, MAX_TEXT)
    if not body:
        return ""
    lang = f" [{msg.lang}]" if msg.lang and msg.lang != "en" else ""
    return f'"{body}"{lang}'
