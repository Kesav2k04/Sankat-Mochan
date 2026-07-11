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
import struct
from dataclasses import dataclass, replace
from typing import Any, ClassVar, Dict, Optional, Union

MAX_BYTES = 244          # ATT payload budget at a 247-byte MTU (247 - 3 ATT header)
DECODE_TOLERANCE = 8     # mirrors the Kotlin side's small slack on inbound size
MAX_ID = 32
MAX_TEXT = 200
MAX_HOPS = 15

TYPES = ("SOS", "DELIVERED", "ACCEPTED")

# --- voice chunks -----------------------------------------------------------
#
# Audio cannot ride the JSON envelope: base64 would cost 33% of a channel that only
# carries ~5 kbps. So a voice chunk is a binary frame, told apart from a JSON envelope
# by its first byte — a JSON envelope always starts with '{' (0x7B), and 0xA5 is not a
# legal UTF-8 lead byte, so the two can never be confused.
#
#   0      magic    0xA5
#   1      version  2
#   2      type     1 = voice chunk, 2 = NACK (resend these pieces)
#   3..6   origin   4 ASCII chars
#   7..8   seq      uint16, which clip
#   9..10  index    uint16, which chunk of that clip  (NACK: 0)
#   11..12 total    uint16, how many chunks the clip has
#   13     hops     uint8
#   14     codec    uint8                             (NACK: 0)
#   15     attempt  uint8, 0 = first transmission
#   16     length   uint8, payload bytes that follow
#   17..            payload
#
# `attempt` is load-bearing. A resent chunk must carry a *different* id, or the mesh's
# dedup — the thing that stops messages looping forever — silently drops the retry as a
# duplicate and the clip can never be repaired.
#
# A NACK's `origin` is the REQUESTER, not the clip's author, so two responders asking
# for the same clip produce two distinct ids. Its payload is the clip's 4-char origin
# followed by a bitmap: bit i of byte i//8 set means "chunk i is missing".
VOICE_MAGIC = 0xA5
VOICE_VERSION = 2
VOICE_TYPE = 1
NACK_TYPE = 2
VOICE_HEADER = 17
VOICE_STRUCT = ">BBB4sHHHBBBB"
MAX_VOICE_CHUNK = 200    # keeps a frame at 217 B — inside LoRa's 255 and the BLE MTU
MAX_VOICE_CHUNKS = 512   # a clip longer than this is not a rescue message
MAX_ATTEMPTS = 7         # first send plus six retries; then the clip is declared lost
CODECS = {1: "ogg/opus", 2: "3gpp/amr-nb"}


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


def _pack(vtype: int, origin: str, seq: int, index: int, total: int,
          hops: int, codec: int, attempt: int, payload: bytes) -> bytes:
    if len(payload) > MAX_VOICE_CHUNK:
        raise ValueError(f"voice payload {len(payload)} > {MAX_VOICE_CHUNK}")
    o = origin.encode("ascii")[:4].ljust(4, b"\0")
    return struct.pack(VOICE_STRUCT, VOICE_MAGIC, VOICE_VERSION, vtype, o, seq, index,
                       total, min(hops, MAX_HOPS), codec, attempt, len(payload)) + payload


@dataclass(frozen=True)
class VoiceChunk:
    """One slice of a recorded voice message, in flight across the mesh.

    Deliberately shaped like [Envelope] — it exposes `id`, `type`, `origin`, `hops`,
    `bumped()` and `encode()` — so the mesh node forwards, deduplicates and logs it
    without knowing what it is. Only the phones ever reassemble a clip.
    """
    origin: str
    seq: int
    index: int
    total: int
    payload: bytes
    hops: int = 0
    codec: int = 1
    attempt: int = 0

    type: ClassVar[str] = "VOICE"

    @property
    def id(self) -> str:
        """Unique per chunk *per attempt*. Mesh dedup must drop a looping copy but must
        never drop a retransmission, or a lost chunk can never be repaired."""
        return f"{self.origin}-v{self.seq}-{self.index}#{self.attempt}"

    @property
    def clip_id(self) -> str:
        return f"{self.origin}-v{self.seq}"

    def bumped(self) -> "VoiceChunk":
        return replace(self, hops=min(self.hops + 1, MAX_HOPS))

    def encode(self) -> bytes:
        return _pack(VOICE_TYPE, self.origin, self.seq, self.index, self.total,
                     self.hops, self.codec, self.attempt, self.payload)


@dataclass(frozen=True)
class VoiceNack:
    """"Clip <clip_origin>-v<seq>: I am missing these pieces." Sent by a receiver whose
    reassembly has stalled; acted on by the phone that recorded the clip."""
    origin: str          # the REQUESTER, so two responders produce two distinct ids
    clip_origin: str     # whose clip this is
    seq: int
    total: int
    missing: tuple
    hops: int = 0
    attempt: int = 0

    type: ClassVar[str] = "VOICE_NACK"

    @property
    def id(self) -> str:
        return f"{self.origin}-n{self.clip_origin}v{self.seq}#{self.attempt}"

    @property
    def clip_id(self) -> str:
        return f"{self.clip_origin}-v{self.seq}"

    def bumped(self) -> "VoiceNack":
        return replace(self, hops=min(self.hops + 1, MAX_HOPS))

    def encode(self) -> bytes:
        bitmap = bytearray((self.total + 7) // 8)
        for i in self.missing:
            bitmap[i // 8] |= 1 << (i % 8)
        body = self.clip_origin.encode("ascii")[:4].ljust(4, b"\0") + bytes(bitmap)
        return _pack(NACK_TYPE, self.origin, self.seq, 0, self.total,
                     self.hops, 0, self.attempt, body)


def _origin_of(raw: bytes) -> Optional[str]:
    try:
        o = raw.rstrip(b"\0").decode("ascii")
    except UnicodeDecodeError:
        return None
    return o if o and o.isalnum() else None


def _decode_voice(raw: bytes):
    """Parse + validate a binary voice frame. Untrusted input (CLAUDE.md #8): every
    field is range-checked and the declared length must match the frame exactly."""
    if len(raw) < VOICE_HEADER or len(raw) > VOICE_HEADER + MAX_VOICE_CHUNK:
        return None
    magic, version, vtype, origin_b, seq, index, total, hops, codec, attempt, length = \
        struct.unpack(VOICE_STRUCT, raw[:VOICE_HEADER])
    if magic != VOICE_MAGIC or version != VOICE_VERSION:
        return None
    if vtype not in (VOICE_TYPE, NACK_TYPE):
        return None
    if not 1 <= total <= MAX_VOICE_CHUNKS:
        return None
    if length > MAX_VOICE_CHUNK or len(raw) != VOICE_HEADER + length:
        return None
    if attempt >= MAX_ATTEMPTS:
        return None
    origin = _origin_of(origin_b)
    if origin is None:
        return None
    body = raw[VOICE_HEADER:]

    if vtype == VOICE_TYPE:
        if codec not in CODECS or index >= total:
            return None
        return VoiceChunk(origin=origin, seq=seq, index=index, total=total,
                          payload=body, hops=min(hops, MAX_HOPS), codec=codec,
                          attempt=attempt)

    # NACK: 4-byte clip origin, then a bitmap covering exactly `total` chunks.
    need = 4 + (total + 7) // 8
    if len(body) != need:
        return None
    clip_origin = _origin_of(body[:4])
    if clip_origin is None:
        return None
    bitmap = body[4:]
    missing = tuple(i for i in range(total) if bitmap[i // 8] >> (i % 8) & 1)
    if not missing:
        return None                      # a NACK asking for nothing is malformed
    return VoiceNack(origin=origin, clip_origin=clip_origin, seq=seq, total=total,
                     missing=missing, hops=min(hops, MAX_HOPS), attempt=attempt)


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


def decode(raw: bytes):
    """Parse + validate. Returns None for anything we should drop on the floor."""
    if not raw:
        return None
    # A JSON envelope always begins '{'. 0xA5 is not a legal UTF-8 lead byte, so the
    # binary voice frame can never be mistaken for one, in either direction.
    if raw[0] == VOICE_MAGIC:
        return _decode_voice(raw)
    if len(raw) > MAX_BYTES + DECODE_TOLERANCE:
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


def describe(msg) -> str:
    """`SOS c363-0 from phone c363, urgency 4/5 (high), near Block C stairwell`."""
    if isinstance(msg, VoiceChunk):
        retry = f", retry {msg.attempt}" if msg.attempt else ""
        return (f"VOICE {msg.clip_id}, from phone {msg.origin}, "
                f"piece {msg.index + 1} of {msg.total} ({len(msg.payload)} bytes of "
                f"{CODECS.get(msg.codec, 'audio')}{retry})")
    if isinstance(msg, VoiceNack):
        n = len(msg.missing)
        return (f"RESEND-REQUEST for {msg.clip_id} from phone {msg.origin}: "
                f"{n} piece{'' if n == 1 else 's'} missing of {msg.total}")
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


def message_text(msg) -> str:
    """The words the victim actually typed, ready to sit on its own log line."""
    if isinstance(msg, (VoiceChunk, VoiceNack)):
        return ""          # audio and control frames have no text to echo
    body = preview(msg.gist, MAX_TEXT)
    if not body:
        return ""
    lang = f" [{msg.lang}]" if msg.lang and msg.lang != "en" else ""
    return f'"{body}"{lang}'
