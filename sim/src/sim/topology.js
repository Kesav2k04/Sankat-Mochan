/**
 * The physical scene: where every node stands, and what kind of radio joins them.
 *
 * Responder coordinates and callsigns are the real seeded roster from
 * `command-post/intelligence.py::_seed_responders`. All positions are lat/lng;
 * the map view owns projection to pixels.
 */

export function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371
  const p1 = (lat1 * Math.PI) / 180
  const p2 = (lat2 * Math.PI) / 180
  const dp = ((lat2 - lat1) * Math.PI) / 180
  const dl = ((lon2 - lon1) * Math.PI) / 180
  const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}

/** Fixed infrastructure. Victims are added dynamically by the scenario. */
export const NODES = {
  P1: { id: 'P1', kind: 'relay', label: 'RELAY P1', sub: 'phone · BLE mesh', lat: 11.702, lng: 76.118 },
  P2: { id: 'P2', kind: 'relay', label: 'RELAY P2', sub: 'phone · BLE mesh', lat: 11.695, lng: 76.136 },
  L1: { id: 'L1', kind: 'lora', label: 'LORA L1', sub: 'field node · BLE+LoRa', lat: 11.69, lng: 76.152 },
  G1: { id: 'G1', kind: 'gateway', label: 'PI GATEWAY', sub: 'LoRa RX · WS uplink', lat: 11.683, lng: 76.18 },
  CP: { id: 'CP', kind: 'cp', label: 'COMMAND POST', sub: 'Snapdragon NPU · offline', lat: 11.6805, lng: 76.186 },
}

/** The seeded roster — ids, callsigns, capabilities and coords from intelligence.py. */
export const RESPONDER_SEED = [
  { id: 'R1', callsign: 'NDRF ALPHA', capability: 'heavy rescue · rope, cutting gear', lat: 11.68, lng: 76.133 },
  { id: 'R2', callsign: 'FIRE BRAVO', capability: 'swift-water · 6 crew', lat: 11.6905, lng: 76.1255 },
  { id: 'R3', callsign: 'MEDIC CHARLIE', capability: 'field medical · O2, stretchers', lat: 11.6832, lng: 76.1402 },
  { id: 'R4', callsign: 'K9 DELTA', capability: 'search dogs · debris survey', lat: 11.6752, lng: 76.1288 },
]

/**
 * Link kinds:
 *   ble  — phone-to-phone, GATT write, ~metres to a few hundred metres
 *   lora — the kilometre gap no phone can cross
 *   wire — Pi to AI-PC, direct Ethernet / WS `/gateway` (EDGE-LINK.md)
 */
export const LINKS = [
  { from: 'P1', to: 'P2', kind: 'ble' },
  { from: 'P2', to: 'L1', kind: 'ble' },
  { from: 'L1', to: 'G1', kind: 'lora' },
  { from: 'G1', to: 'CP', kind: 'wire' },
  { from: 'L1', to: 'R1', kind: 'ble' },
  { from: 'L1', to: 'R2', kind: 'ble' },
  { from: 'L1', to: 'R3', kind: 'ble' },
  { from: 'L1', to: 'R4', kind: 'ble' },
]

export function linkKind(from, to) {
  const l = LINKS.find(
    (x) => (x.from === from && x.to === to) || (x.from === to && x.to === from),
  )
  if (l) return l.kind
  return 'ble' // victim -> nearest relay is always a BLE hop
}

// ---- pixel-space geometry (the map view projects lat/lng -> px first) -------

/** LoRa links bow outward so a radio hop reads differently from a wired one. */
export function edgeGeoPx(p0, p1, kind) {
  if (kind !== 'lora') return { p0, p1, c: null }
  const mx = (p0.x + p1.x) / 2
  const my = (p0.y + p1.y) / 2
  const dx = p1.x - p0.x
  const dy = p1.y - p0.y
  const len = Math.hypot(dx, dy) || 1
  const bow = len * 0.16
  return { p0, p1, c: { x: mx - (dy / len) * bow, y: my + (dx / len) * bow } }
}

export function pointOnEdge(geo, t) {
  const { p0, p1, c } = geo
  if (!c) return { x: p0.x + (p1.x - p0.x) * t, y: p0.y + (p1.y - p0.y) * t }
  const u = 1 - t
  return {
    x: u * u * p0.x + 2 * u * t * c.x + t * t * p1.x,
    y: u * u * p0.y + 2 * u * t * c.y + t * t * p1.y,
  }
}

export function edgePath(geo) {
  const { p0, p1, c } = geo
  if (!c) return `M ${p0.x} ${p0.y} L ${p1.x} ${p1.y}`
  return `M ${p0.x} ${p0.y} Q ${c.x} ${c.y} ${p1.x} ${p1.y}`
}
