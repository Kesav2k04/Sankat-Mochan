/**
 * CONTRACT 1 — the SOS envelope, as it goes on the air.
 *
 * A JS port of `raspberrypi/envelope.py` (which is itself a port of the Android
 * `model/SosMessage.kt`). Same short keys, same 244-byte budget, same
 * gist-trimming rule. The simulator encodes real bytes so the inspector shows
 * what actually crosses the radio, not a pretty-printed stand-in.
 */

const enc = new TextEncoder()

export const MAX_BYTES = 244 // ATT payload budget at a 247-byte MTU
export const MAX_HOPS = 15

// Binary voice frame header, ">BBB4sHHHBBBB" = 17 bytes. See envelope.py.
export const VOICE_MAGIC = 0xa5
export const VOICE_VERSION = 2
export const VOICE_HEADER = 17
export const MAX_VOICE_CHUNK = 200
export const CODECS = { 1: 'ogg/opus', 2: '3gpp/amr-nb' }

export function byteLen(s) {
  return enc.encode(s).length
}

/** Compact small-key form. Key order matches envelope.py's to_dict(). */
export function toWire(e) {
  const o = { i: e.id, t: e.type, o: e.origin }
  if (e.refId != null) o.r = e.refId
  o.u = e.urgency
  o.c = e.category
  o.l = e.locationHint ?? ''
  o.g = e.gist
  o.ln = e.lang
  if (e.lat != null && e.lng != null) {
    o.la = e.lat
    o.lo = e.lng
  }
  o.ts = e.ts
  o.h = e.hops
  return o
}

/**
 * UTF-8 JSON, <= MAX_BYTES. Only the free-text gist is trimmed, one CHARACTER
 * at a time — the Kotlin original drops a byte count from a character string,
 * which throws away the whole gist for Tamil/Hindi. envelope.py fixed that; so
 * does this.
 */
export function encode(e) {
  let gist = e.gist ?? ''
  let json = JSON.stringify(toWire({ ...e, gist }))
  let trimmed = 0
  while (byteLen(json) > MAX_BYTES && gist.length) {
    gist = gist.slice(0, -1)
    trimmed++
    json = JSON.stringify(toWire({ ...e, gist }))
  }
  return { json, bytes: enc.encode(json), trimmed }
}

/**
 * Short content hash, logged at TX and again at RX so a reader can confirm the
 * exact bytes crossed the air. The real gateway uses sha256[:12]; the browser's
 * only SHA-256 is async, so this is FNV-1a/64 — same purpose, different function.
 */
export function digest(bytes) {
  let h = 0xcbf29ce484222325n
  const prime = 0x100000001b3n
  const mask = 0xffffffffffffffffn
  for (const b of bytes) {
    h = ((h ^ BigInt(b)) * prime) & mask
  }
  return h.toString(16).padStart(16, '0').slice(0, 12)
}

export function hexdump(bytes, cols = 16) {
  const rows = []
  for (let off = 0; off < bytes.length; off += cols) {
    const slice = Array.from(bytes.slice(off, off + cols))
    rows.push({
      off: off.toString(16).padStart(4, '0'),
      hex: slice.map((b) => b.toString(16).padStart(2, '0')),
      ascii: slice.map((b) => (b >= 0x20 && b < 0x7f ? String.fromCharCode(b) : '·')).join(''),
    })
  }
  return rows
}

/** Build the 17-byte voice-chunk header exactly as `_pack()` does. */
export function voiceHeader({ origin, seq, index, total, hops, codec = 1, attempt = 0, length }) {
  const buf = new Uint8Array(VOICE_HEADER)
  const dv = new DataView(buf.buffer)
  dv.setUint8(0, VOICE_MAGIC)
  dv.setUint8(1, VOICE_VERSION)
  dv.setUint8(2, 1) // type 1 = voice chunk
  const o = enc.encode(origin).slice(0, 4)
  buf.set(o, 3)
  dv.setUint16(7, seq)
  dv.setUint16(9, index)
  dv.setUint16(11, total)
  dv.setUint8(13, Math.min(hops, MAX_HOPS))
  dv.setUint8(14, codec)
  dv.setUint8(15, attempt)
  dv.setUint8(16, length)
  return buf
}

/**
 * LoRa time-on-air, Semtech AN1200.13.
 *
 * This is why the LoRa hop in the simulator is slow: 244 bytes at SF9/BW125 is
 * genuinely ~1.2 seconds of airtime. The number on screen is computed, not typed.
 */
export function loraAirtimeMs({ payload, sf = 9, bw = 125000, cr = 1, preamble = 8, explicitHeader = true, lowDataRateOptimize = null }) {
  const tSym = Math.pow(2, sf) / bw // seconds
  const tPreamble = (preamble + 4.25) * tSym
  const de = lowDataRateOptimize ?? (sf >= 11 ? 1 : 0)
  const h = explicitHeader ? 0 : 1
  const num = 8 * payload - 4 * sf + 28 + 16 - 20 * h
  const den = 4 * (sf - 2 * de)
  const nPayload = 8 + Math.max(Math.ceil(num / den) * (cr + 4), 0)
  const tPayload = nPayload * tSym
  return {
    airtimeMs: (tPreamble + tPayload) * 1000,
    symbols: nPayload,
    tSymMs: tSym * 1000,
    bitrateBps: sf * (bw / Math.pow(2, sf)) * (4 / (4 + cr)),
  }
}

export const LORA_RADIO = {
  band: 'IN865',
  freqMHz: 865.0625, // India ISM 865–867 MHz, license-free
  sf: 9,
  bwKHz: 125,
  crLabel: '4/5',
  txDbm: 14,
}
