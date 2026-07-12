// Unit tests for the simulator's wire layer — must stay byte-compatible with
// raspberrypi/envelope.py (CONTRACT 1) and the Semtech AN1200.13 airtime math.
import { describe, expect, it } from 'vitest'
import {
  MAX_BYTES, MAX_VOICE_CHUNK, VOICE_HEADER, VOICE_MAGIC, VOICE_VERSION,
  byteLen, digest, encode, hexdump, loraAirtimeMs, toWire, voiceHeader,
} from '../src/sim/envelope.js'

const TAMIL = 'தண்ணீர் வேகமாக ஏறுகிறது, நாங்கள் மாடியில் சிக்கிக்கொண்டோம்'

const sos = (over = {}) => ({
  id: 'v1-0', type: 'SOS', origin: 'v1', urgency: 5, category: 'trapped',
  locationHint: 'upper floor', gist: 'water rising', lang: 'ta',
  lat: 11.6995, lng: 76.0605, ts: 1752100000, hops: 0, ...over,
})

describe('toWire', () => {
  it('uses the short-key contract in envelope.py order', () => {
    const keys = Object.keys(toWire(sos()))
    expect(keys).toEqual(['i', 't', 'o', 'u', 'c', 'l', 'g', 'ln', 'la', 'lo', 'ts', 'h'])
  })
  it('omits coords unless both are present, and refId unless set', () => {
    const wire = toWire(sos({ lat: null }))
    expect(wire).not.toHaveProperty('la')
    expect(wire).not.toHaveProperty('lo')
    expect(wire).not.toHaveProperty('r')
    expect(toWire(sos({ refId: 'v1-0' })).r).toBe('v1-0')
  })
})

describe('encode', () => {
  it('fits the 244-byte budget without trimming a short gist', () => {
    const { bytes, trimmed } = encode(sos())
    expect(bytes.length).toBeLessThanOrEqual(MAX_BYTES)
    expect(trimmed).toBe(0)
  })
  it('trims Indic text by characters, keeping a usable prefix', () => {
    const { json, bytes, trimmed } = encode(sos({ gist: TAMIL.repeat(4) }))
    expect(bytes.length).toBeLessThanOrEqual(MAX_BYTES)
    expect(trimmed).toBeGreaterThan(0)
    const gist = JSON.parse(json).g
    expect(gist.length).toBeGreaterThan(5)          // not wiped out
    expect(TAMIL.repeat(4).startsWith(gist)).toBe(true)
  })
  it('multibyte byteLen is bytes, not chars', () => {
    expect(byteLen('abc')).toBe(3)
    expect(byteLen('தமிழ்')).toBeGreaterThan(5)
  })
})

describe('digest (FNV-1a/64)', () => {
  it('is deterministic, 12 hex chars, and content-sensitive', () => {
    const a = encode(sos()).bytes
    expect(digest(a)).toBe(digest(a))
    expect(digest(a)).toMatch(/^[0-9a-f]{12}$/)
    expect(digest(a)).not.toBe(digest(new Uint8Array([...a, 32])))
  })
})

describe('voiceHeader', () => {
  it('packs the 17-byte contract like envelope.py _pack()', () => {
    const buf = voiceHeader({ origin: 'ph1', seq: 7, index: 3, total: 9, hops: 99, codec: 2, attempt: 1, length: 120 })
    expect(buf.length).toBe(VOICE_HEADER)
    const dv = new DataView(buf.buffer)
    expect(dv.getUint8(0)).toBe(VOICE_MAGIC)
    expect(dv.getUint8(1)).toBe(VOICE_VERSION)
    expect(dv.getUint8(2)).toBe(1)
    expect(dv.getUint16(7)).toBe(7)
    expect(dv.getUint16(9)).toBe(3)
    expect(dv.getUint16(11)).toBe(9)
    expect(dv.getUint8(13)).toBe(15)                 // hops clamped to MAX_HOPS
    expect(dv.getUint8(14)).toBe(2)
    expect(dv.getUint8(15)).toBe(1)
    expect(dv.getUint8(16)).toBe(120)
    expect(120).toBeLessThanOrEqual(MAX_VOICE_CHUNK)
  })
})

describe('loraAirtimeMs (Semtech AN1200.13)', () => {
  it('gives ~1.2 s for a full envelope at SF9/BW125 CR4/5', () => {
    const { airtimeMs, symbols } = loraAirtimeMs({ payload: 244 })
    expect(airtimeMs).toBeGreaterThan(1100)
    expect(airtimeMs).toBeLessThan(1300)
    expect(symbols).toBe(283)
  })
  it('is monotonic in payload size and applies LDRO at SF11+', () => {
    const small = loraAirtimeMs({ payload: 20 }).airtimeMs
    const big = loraAirtimeMs({ payload: 200 }).airtimeMs
    expect(big).toBeGreaterThan(small)
    const sf11 = loraAirtimeMs({ payload: 100, sf: 11 })
    expect(sf11.airtimeMs).toBeGreaterThan(loraAirtimeMs({ payload: 100 }).airtimeMs)
  })
})

describe('hexdump', () => {
  it('renders offsets, hex and printable ascii', () => {
    const rows = hexdump(new TextEncoder().encode('{"i":"x"}'))
    expect(rows[0].off).toBe('0000')
    expect(rows[0].ascii.startsWith('{"i"')).toBe(true)
  })
})
