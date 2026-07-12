/**
 * The simulation, in the order the real system works:
 *
 *   1. UPLINK — the SOS (text + voice note) leaves the danger spot. Every
 *      module around the spot hears the broadcast, but only the SHORTEST
 *      route relays it on: priority one is reaching the safe camp.
 *      Rangers who happen to be in range OVERHEAR it — awareness only,
 *      nobody self-dispatches.
 *   2. AT THE SAFE CAMP — the voice note is transcribed offline, triaged,
 *      and a supplies list is suggested from what the victim actually said.
 *   3. DOWNLINK — the camp tasks the nearest ranger over the same mesh.
 *      The ranger accepts; the acceptance travels back so command knows;
 *      the victim is told "help is on the way" in their own language.
 *   4. RESPONSE — the tasked ranger moves to the spot with the supplies.
 */

import { encode, loraAirtimeMs } from './envelope.js'

export const ZONE = { lat: 11.685, lng: 76.132, radiusKm: 10 }
export const OUTPOST = { id: 'OUTPOST', label: 'SAFE CAMP · OUTPOST', lat: 11.635, lng: 76.225 }
/** Where the SOS originates — deep inside the zone, far from the outpost. */
export const DANGER_SPOT = { id: 'SPOT', label: 'DANGER SPOT', lat: 11.6995, lng: 76.0605 }
export const RANGE_KM = 5 // rural LoRa link budget, SF9–SF12 class
export const MAX_NODES = 20
const ACCEPT_S = 1.4 // a ranger takes a beat to tap Accept
const HOP_S = 1.2 // watchable hop: ~1.1 s real airtime + processing

export function haversineKm(a, b) {
  const R = 6371
  const p1 = (a.lat * Math.PI) / 180
  const p2 = (b.lat * Math.PI) / 180
  const dp = ((b.lat - a.lat) * Math.PI) / 180
  const dl = ((b.lng - a.lng) * Math.PI) / 180
  const s = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(s))
}

export function inZone(p) {
  return haversineKm(p, ZONE) <= ZONE.radiusKm
}

/** A point `km` from `center` at bearing `deg` — geometrically accurate on the map. */
function ringPoint(center, km, deg) {
  const a = (deg * Math.PI) / 180
  return {
    lat: center.lat + (km / 111.32) * Math.cos(a),
    lng: center.lng + (km / (111.32 * Math.cos((center.lat * Math.PI) / 180))) * Math.sin(a),
  }
}

/**
 * Default layout: an accurate CIRCLE of eight modules around the danger spot
 * (2 km out, so the first broadcast is heard from every side), a relay chain to
 * the outpost, plus a few modules scattered at random across the zone — a real
 * deployment is never tidy. The router ignores whatever doesn't help: only the
 * shortest route to the camp carries the message.
 */
export function autoLayout() {
  const ring = []
  for (let k = 0; k < 8; k++) ring.push(ringPoint(DANGER_SPOT, 2, k * 45))

  const chain = [
    { lat: 11.698, lng: 76.105 },
    { lat: 11.686, lng: 76.14 },
    { lat: 11.67, lng: 76.172 },
    { lat: 11.655, lng: 76.2 },
  ]

  const scatter = []
  for (let k = 0; k < 5; k++) {
    const km = 3.5 + Math.random() * 5.5 // anywhere in the zone, away from the spot
    scatter.push(ringPoint(ZONE, km * 0.9, Math.random() * 360))
  }

  return [...ring, ...chain, ...scatter].filter(inZone)
}

/** The real wire cost of one hop — encoded envelope bytes through the Semtech formula. */
export const SOS_WIRE = (() => {
  const { bytes } = encode({
    id: 'v1-0',
    type: 'SOS',
    origin: 'v1',
    urgency: 5,
    category: 'trapped',
    locationHint: '',
    gist: 'மாடியில் சிக்கினேன், தண்ணீர் ஏறுகிறது',
    lang: 'ta',
    lat: DANGER_SPOT.lat,
    lng: DANGER_SPOT.lng,
    ts: 1752100000,
    hops: 0,
  })
  return { bytes: bytes.length, airtimeMs: loraAirtimeMs({ payload: bytes.length }).airtimeMs }
})()

/** What the offline AI makes of the victim's voice note at the safe camp. */
export const VOICE_TRIAGE = {
  transcript: 'Trapped on the upper floor — the water is rising',
  lang: 'Tamil',
  urgency: 5,
  category: 'trapped · flood',
  supplies: ['rope & harness', 'flotation vests', 'first-aid kit', 'stretcher', 'drinking water', 'thermal blanket'],
}

/** Every radio link that closes: module↔module and module↔outpost within range. */
export function buildLinks(nodes) {
  const pts = [...nodes, OUTPOST]
  const links = []
  for (let i = 0; i < pts.length; i++)
    for (let j = i + 1; j < pts.length; j++) {
      const km = haversineKm(pts[i], pts[j])
      if (km <= RANGE_KM) links.push({ a: pts[i], b: pts[j], km })
    }
  return links
}

/** Shortest radio path (by total km) from `from` to `to` over the mesh. Null if broken. */
export function route(nodes, from, to) {
  const pts = [...new Set([from, ...nodes, to])]
  const dist = new Map(pts.map((p) => [p, Infinity]))
  const prev = new Map()
  dist.set(from, 0)
  const open = new Set(pts)
  while (open.size) {
    let u = null
    for (const p of open) if (u === null || dist.get(p) < dist.get(u)) u = p
    open.delete(u)
    if (u === to || dist.get(u) === Infinity) break
    for (const v of open) {
      const km = haversineKm(u, v)
      if (km > RANGE_KM) continue
      const alt = dist.get(u) + km
      if (alt < dist.get(v)) {
        dist.set(v, alt)
        prev.set(v, u)
      }
    }
  }
  if (dist.get(to) === Infinity) return null
  const path = []
  for (let p = to; p; p = prev.get(p)) path.unshift(p)
  return { path, km: dist.get(to) }
}

function pathKm(path) {
  let km = 0
  for (let i = 0; i < path.length - 1; i++) km += haversineKm(path[i], path[i + 1])
  return km
}

/**
 * The victim's first broadcast is heard by EVERY module in range of the spot.
 * The mesh then relays via whichever of them starts the shortest total route
 * to the outpost — that route and only that route carries the message on.
 */
export function bestOrigin(nodes) {
  const heard = nodes.filter((n) => haversineKm(n, DANGER_SPOT) <= RANGE_KM)
  let best = null
  for (const n of heard) {
    const r = route(nodes, n, OUTPOST)
    if (!r) continue
    const total = haversineKm(DANGER_SPOT, n) + r.km
    if (!best || total < best.km) best = { origin: n, path: r.path, km: total }
  }
  return { heard: heard.length, origin: best?.origin ?? null, path: best?.path ?? null, km: best?.km ?? Infinity }
}

/** Rangers patrol near the relay chain — deterministic offsets from two path modules. */
export function placeRangers(path) {
  const mods = path.slice(0, -1)
  const near = (n, dlat, dlng, id, label) => ({ id, label, lat: n.lat + dlat, lng: n.lng + dlng })
  const a = mods[Math.min(1, mods.length - 1)]
  const b = mods[Math.max(0, mods.length - 2)]
  return [near(a, 0.011, 0.009, 'R1', 'RANGER 1'), near(b, -0.013, -0.011, 'R2', 'RANGER 2')]
}

function name(p, nodes) {
  if (p.id === 'OUTPOST') return 'SAFE CAMP'
  if (p.id === 'VICTIM' || p.id === 'SPOT') return 'VICTIM'
  return `LORA-${nodes.indexOf(p) + 1}`
}

export function buildTimeline(nodes) {
  const { heard, origin, path } = bestOrigin(nodes)
  if (!origin || !path) return null

  const victim = { id: 'VICTIM', label: 'VICTIM', lat: DANGER_SPOT.lat, lng: DANGER_SPOT.lng }
  const rangers = placeRangers(path)

  const segs = []
  const events = []
  let t = 0

  // ---- 1. UPLINK — priority one: reach the safe camp -----------------------
  events.push({ t, text: `SOS + voice note recorded at the danger spot — ${SOS_WIRE.bytes} B envelope + audio` })
  segs.push({ kind: 'speak', at: victim, t0: t, dur: 1.8 })
  t += 1.8

  events.push({
    t,
    text: `${heard} module${heard > 1 ? 's' : ''} around the spot hear the broadcast — shortest route wins: ${name(origin, nodes)}, ${pathKm([victim, ...path]).toFixed(1)} km total to the camp`,
  })
  segs.push({ kind: 'hop', pkt: 'SOS', from: victim, to: origin, t0: t, dur: 0.8 })
  t += 0.8

  const overhear = new Map() // ranger id -> t (awareness only — nobody self-dispatches)
  for (let i = 0; i < path.length - 1; i++) {
    const from = path[i]
    events.push({ t, text: `${name(from, nodes)} relays — ${SOS_WIRE.airtimeMs.toFixed(0)} ms on air` })
    for (const r of rangers) {
      if (!overhear.has(r.id) && haversineKm(r, from) <= RANGE_KM) {
        overhear.set(r.id, t)
        events.push({ t: t + 0.3, text: `${r.label} overhears the SOS — monitoring, awaiting tasking from the camp`, tone: 'warn' })
      }
    }
    segs.push({ kind: 'hop', pkt: 'SOS', from, to: path[i + 1], t0: t, dur: HOP_S })
    t += HOP_S
  }

  const hops = path.length - 1
  const outpostAt = t
  events.push({ t, text: `SAFE CAMP received the SOS — ${hops} hops, ${t.toFixed(1)} s. Priority delivery complete.`, tone: 'good' })

  // ---- 2. AT THE SAFE CAMP — transcribe, triage, suggest supplies ----------
  t += 0.9
  events.push({ t, text: `Voice note transcribed offline (${VOICE_TRIAGE.lang}): “${VOICE_TRIAGE.transcript}”` })
  t += 1.0
  const triageAt = t
  events.push({
    t,
    text: `AI triage: urgency ${VOICE_TRIAGE.urgency}/5 · ${VOICE_TRIAGE.category} — suggested supplies: ${VOICE_TRIAGE.supplies.slice(0, 4).join(', ')}…`,
    tone: 'good',
  })

  // ---- 3. DOWNLINK — the camp tasks the nearest ranger ---------------------
  const responder = [...rangers].sort((a, b) => haversineKm(a, victim) - haversineKm(b, victim))[0]
  const rkm = haversineKm(responder, victim)
  const rmod = [...nodes].sort((a, b) => haversineKm(a, responder) - haversineKm(b, responder))[0]
  const down = route(nodes, rmod, OUTPOST)
  if (!down) return null
  const downPath = [...down.path].reverse() // outpost -> ... -> ranger's module

  t += 0.8
  const dispatchAt = t
  events.push({
    t,
    text: `SAFE CAMP tasks ${responder.label} — nearest to the spot (${rkm.toFixed(1)} km). Dispatch + supplies list sent back over LoRa, shortest route.`,
    tone: 'warn',
  })
  for (let i = 0; i < downPath.length - 1; i++) {
    segs.push({ kind: 'hop', pkt: 'DISPATCH', from: downPath[i], to: downPath[i + 1], t0: t, dur: HOP_S })
    t += HOP_S
  }

  const task = { rid: responder.id, via: rmod, tAlert: t, tAccept: t + ACCEPT_S }
  events.push({ t, text: `${name(rmod, nodes)} alerts ${responder.label} — task received`, tone: 'warn' })
  t += ACCEPT_S
  events.push({ t, text: `${responder.label} ACCEPTED the task`, tone: 'good' })
  const acceptAt = t

  // The victim is told FIRST: "HELP ACCEPTED" races from the ranger's own
  // module straight back to the spot — it does not wait for the camp round-trip.
  let ta = acceptAt
  events.push({ t: ta, text: `HELP ACCEPTED races back to the victim — priority over everything else`, tone: 'good' })
  const back = route(nodes, rmod, origin)
  const backPath = back ? back.path : [rmod]
  for (let i = 0; i < backPath.length - 1; i++) {
    segs.push({ kind: 'hop', pkt: 'ACK', from: backPath[i], to: backPath[i + 1], t0: ta, dur: HOP_S })
    ta += HOP_S
  }
  segs.push({ kind: 'hop', pkt: 'ACK', from: origin, to: victim, t0: ta, dur: 0.8 })
  ta += 0.8
  const victimAckAt = ta
  events.push({ t: ta, text: `Victim hears it in ${VOICE_TRIAGE.lang}: “Help is on the way”`, tone: 'good' })

  // ...while the acceptance confirms back to the camp in parallel
  let tc = acceptAt
  for (let i = 0; i < down.path.length - 1; i++) {
    segs.push({ kind: 'hop', pkt: 'ACCEPT', from: down.path[i], to: down.path[i + 1], t0: tc, dur: HOP_S })
    tc += HOP_S
  }
  events.push({ t: tc, text: `Acceptance confirmed at SAFE CAMP — ${responder.label} is committed`, tone: 'good' })
  t = Math.max(ta, tc)

  // ---- 4. RESPONSE — the tasked ranger moves, in parallel with the ACK -----
  const goAt = acceptAt + 0.4
  events.push({ t: goAt, text: `${responder.label} moving with supplies — ${rkm.toFixed(1)} km to the danger spot`, tone: 'warn' })
  segs.push({ kind: 'respond', ranger: responder.id, from: responder, to: victim, t0: goAt, dur: 11 })
  events.push({ t: goAt + 11, text: `${responder.label} reached the victim`, tone: 'good' })

  const total = Math.max(goAt + 11, victimAckAt) + 0.5
  events.sort((a, b) => a.t - b.t)

  return {
    victim,
    rangers,
    path,
    segs,
    events,
    overhear,
    task,
    responder: responder.id,
    triage: { t: triageAt, ...VOICE_TRIAGE },
    dispatchAt,
    victimAckAt,
    total,
    outpostAt,
    hops,
  }
}
