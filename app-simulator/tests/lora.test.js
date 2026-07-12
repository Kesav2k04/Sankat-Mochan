// Unit tests for the mesh/routing model behind the demo — real geometry, real
// shortest-path, real airtime, so the story on screen is computed, not staged.
import { describe, expect, it } from 'vitest'
import {
  DANGER_SPOT, OUTPOST, RANGE_KM, SOS_WIRE, ZONE,
  autoLayout, bestOrigin, buildLinks, buildTimeline, haversineKm, inZone, route,
} from '../src/sim/lora.js'

describe('haversineKm', () => {
  it('is zero for identical points and symmetric', () => {
    expect(haversineKm(ZONE, ZONE)).toBe(0)
    expect(haversineKm(DANGER_SPOT, OUTPOST)).toBeCloseTo(haversineKm(OUTPOST, DANGER_SPOT), 10)
  })
  it('measures the spot-to-outpost gap as a multi-hop distance', () => {
    const km = haversineKm(DANGER_SPOT, OUTPOST)
    expect(km).toBeGreaterThan(RANGE_KM)   // one LoRa hop cannot cross it...
    expect(km).toBeLessThan(30)            // ...but it is still inside the zone scale
  })
})

describe('zone + layout', () => {
  it('autoLayout stays inside the operating zone', () => {
    for (const n of autoLayout()) expect(inZone(n)).toBe(true)
  })
  it('always places the 12 deterministic modules (ring of 8 + chain of 4)', () => {
    expect(autoLayout().length).toBeGreaterThanOrEqual(12)
  })
})

describe('routing', () => {
  it('finds a relay route from the danger spot to the outpost on the default layout', () => {
    const nodes = autoLayout()
    const { heard, origin, path, km } = bestOrigin(nodes)
    expect(heard).toBeGreaterThan(0)
    expect(origin).not.toBeNull()
    expect(path[path.length - 1]).toBe(OUTPOST)
    // every hop on the chosen route must close a real radio link
    for (let i = 0; i < path.length - 1; i++) {
      expect(haversineKm(path[i], path[i + 1])).toBeLessThanOrEqual(RANGE_KM)
    }
    expect(km).toBeGreaterThan(haversineKm(DANGER_SPOT, OUTPOST) * 0.9) // no teleporting
  })
  it('returns null when the chain is broken', () => {
    const lonely = [{ lat: DANGER_SPOT.lat + 0.01, lng: DANGER_SPOT.lng }]
    expect(route(lonely, DANGER_SPOT, OUTPOST)).toBeNull()
  })
  it('buildLinks only closes links within radio range', () => {
    for (const l of buildLinks(autoLayout())) expect(l.km).toBeLessThanOrEqual(RANGE_KM)
  })
})

describe('the demo timeline is physically honest', () => {
  it('encodes a real envelope and computes its airtime', () => {
    expect(SOS_WIRE.bytes).toBeLessThanOrEqual(244)
    expect(SOS_WIRE.airtimeMs).toBeGreaterThan(1000)
  })
  it('builds a full uplink→triage→dispatch→response timeline', () => {
    const tl = buildTimeline(autoLayout())
    expect(tl).not.toBeNull()
    expect(tl.events.length).toBeGreaterThan(5)
    expect(tl.segs.length).toBeGreaterThan(5)
  })
})
