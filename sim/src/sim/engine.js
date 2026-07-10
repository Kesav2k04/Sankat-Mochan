/**
 * The simulator core.
 *
 * Every SOS is a `journey`: an ordered list of phases, each either a pause at a
 * node (speak, transcribe, triage) or a traversal of one link (a BLE hop, the
 * LoRa hop, the Ethernet hop to the AI PC). Advancing a journey is what makes a
 * packet move on screen; side effects fire when a phase is entered or left.
 *
 * The orchestration rules mirror `command-post/intelligence.py`: code owns the
 * source of truth and every automated decision, and the "LLM" is consulted only
 * for the fuzzy parts (translate / urgency). Nothing here lets a message's
 * contents steer control flow — an SOS is data, never a command.
 */

import { encode, digest, loraAirtimeMs, MAX_BYTES } from './envelope.js'
import { NODES, RESPONDER_SEED, haversineKm, linkKind } from './topology.js'
import { TRACE_SOS, buildSurge, SURGE_DAY_SCALE } from './scenario.js'

// ---- Tunables, matching intelligence.py ------------------------------------
const CLUSTER_EPS_M = 100 // C1: split-biased — never merge two distinct emergencies
const AGING_CAP_BOOST = 0.5 // C3: bounded aging, never lifts out of tier
const AGING_HALF_LIFE_S = 15 * 60
const RESPONDER_SPEED_KMH = 12 // C5: rough field speed for the approx ETA

// ---- Link timings ----------------------------------------------------------
const BLE_S = 0.09 // one GATT write at a 247-byte MTU
const WIRE_S = 0.02 // Pi -> AI PC over direct Ethernet
const VOICE_HOP_S = 0.1

/**
 * Marker motion is time-compressed; the ETA shown to the operator is not.
 * In SURGE the compression is the scenario's own day-scale, so travel and
 * on-scene work shrink by exactly the same factor as everything else on the
 * clock. In TRACE the clock runs at 1×, so a separate factor keeps a 17-minute
 * drive watchable.
 */
const TRAVEL_COMPRESS = 60

/** A landslide extraction is not instantaneous. This is what occupies a crew. */
const ON_SCENE_MIN = 45

const ACTIVE_STATES = new Set(['triaged', 'clustered', 'holding', 'proposed', 'assigned', 'en route', 'on-scene'])

function fmt(n, d = 1) {
  return Number(n.toFixed(d))
}

export class Sim {
  constructor() {
    this.reset('trace')
  }

  // ---------------------------------------------------------------- lifecycle
  reset(mode, crews = 4) {
    this.mode = mode
    this.crews = crews
    this.clock = 0
    this.rev = 0
    this.logSeq = 0
    this.journeys = []
    this.victims = {}
    this.incidents = new Map()
    this.activity = []
    this.packets = []
    this.pulses = []
    this.radioTx = []
    this.focusId = null
    this.warp = 1
    this.finished = false

    // Crews beyond the staffing level stay offline: never proposed, never counted.
    this.responders = {}
    RESPONDER_SEED.forEach((r, i) => {
      this.responders[r.id] = {
        ...r,
        base: { lat: r.lat, lng: r.lng },
        status: i < crews ? 'available' : 'offline',
        assignedIncident: null,
        motion: null,
      }
    })

    this.metrics = {
      pktRx: 0,
      bytesRx: 0,
      resolved: 0,
      decisionTimes: [],
      triageLatencies: [],
      etaMinutes: [],
    }

    this.dayScale = mode === 'surge' ? SURGE_DAY_SCALE : 1
    this.pending = mode === 'surge' ? buildSurge().map((s) => ({ ...s })) : [{ ...TRACE_SOS, t: 0.4 }]
    this.total = this.pending.length

    this.log(
      mode === 'surge'
        ? `SURGE — 24 h of the Wayanad landslide, ${this.total} SOS, compressed. Triage cached for deterministic playback.`
        : 'TRACE — one SOS, real time, every hop.',
    )
    this.rev++
  }

  log(text) {
    // Monotonic id: `activity.length` would repeat once the list caps at 300,
    // handing React duplicate keys and scrambling the log.
    this.activity = [{ ts: this.clock, text, id: this.logSeq++ }, ...this.activity].slice(0, 300)
  }

  // ------------------------------------------------------------------ helpers
  nodeOf(id) {
    return this.victims[id] ?? this.responders[id] ?? NODES[id]
  }

  /** Which relay phone can this victim's phone actually reach over BLE? */
  nearestRelay(sos) {
    if (sos.lat == null) {
      // No GPS fix. It still gets in — via whichever relay heard it.
      return sos.origin.charCodeAt(0) % 2 === 0 ? 'P1' : 'P2'
    }
    const d1 = haversineKm(sos.lat, sos.lng, NODES.P1.lat, NODES.P1.lng)
    const d2 = haversineKm(sos.lat, sos.lng, NODES.P2.lat, NODES.P2.lng)
    return d1 <= d2 ? 'P1' : 'P2'
  }

  // -------------------------------------------------------------------- spawn
  spawn(sos) {
    const vid = `V:${sos.origin}`
    const relay = this.nearestRelay(sos)
    const anchor = NODES[relay]

    // A no-fix victim is drawn at the relay that heard them, ringed to say so.
    this.victims[vid] = {
      id: vid,
      kind: 'victim',
      label: sos.origin,
      relay,
      lat: sos.lat ?? anchor.lat + 0.0022,
      lng: sos.lng ?? anchor.lng - 0.0035,
      noFix: sos.lat == null,
      urgency: sos.ai.urgency,
    }

    const { json, bytes, trimmed } = encode(sos)
    const upPath = relay === 'P1' ? [vid, 'P1', 'P2', 'L1', 'G1', 'CP'] : [vid, 'P2', 'L1', 'G1', 'CP']
    const lora = loraAirtimeMs({ payload: bytes.length })

    const j = {
      id: sos.id,
      sos,
      vid,
      relay,
      upPath,
      wire: { json, bytes, digest: digest(bytes), trimmed },
      lora,
      hops: 0,
      pi: 0,
      pt: 0,
      done: false,
      state: 'in flight',
      incidentId: null,
      responderId: null,
      etaMin: null,
      tIngest: null,
      heldLogged: false,
      voiceState: null,
      phases: this.buildUpPhases(sos, vid, upPath, bytes, lora),
    }
    this.journeys.push(j)
    if (!this.focusId) this.focusId = j.id
    this.enter(j, j.phases[0])
    this.rev++
  }

  buildUpPhases(sos, vid, upPath, bytes, lora) {
    const P = []
    P.push({ k: 'speak', kind: 'node', node: vid, dur: 2.2, label: 'Victim speaks', detail: 'phone records · nothing leaves the device' })
    if (sos.voice) {
      P.push({ k: 'stt', kind: 'node', node: vid, dur: 0.8, label: 'On-device transcription', detail: 'Whisper · NPU · offline' })
    }
    P.push({
      k: 'encode',
      kind: 'node',
      node: vid,
      dur: 0.35,
      label: 'Envelope sealed',
      detail: `${bytes.length} B of ${MAX_BYTES} · CONTRACT 1`,
    })

    for (let i = 0; i < upPath.length - 1; i++) {
      const from = upPath[i]
      const to = upPath[i + 1]
      const kind = linkKind(from, to)
      const dur = kind === 'lora' ? lora.airtimeMs / 1000 : kind === 'wire' ? WIRE_S : BLE_S
      P.push({
        k: 'up',
        kind: 'edge',
        from,
        to,
        link: kind,
        pkt: 'SOS',
        dur,
        label:
          kind === 'lora'
            ? 'LoRa hop — the kilometre gap'
            : kind === 'wire'
              ? 'Gateway → AI PC'
              : 'BLE mesh hop',
        detail:
          kind === 'lora'
            ? `SF9/BW125 · ${fmt(lora.airtimeMs)} ms airtime · ${bytes.length} B`
            : kind === 'wire'
              ? 'WS /gateway · durable outbox until ACK'
              : 'GATT write · store-and-forward',
      })
    }

    P.push({ k: 'ack', kind: 'edge', from: 'CP', to: 'G1', link: 'wire', pkt: 'ACK', dur: WIRE_S, label: 'ACK', detail: 'outbox row deleted only now' })
    P.push({ k: 'triage', kind: 'node', node: 'CP', dur: (sos.ai.latencyMs ?? 1400) / 1000, label: 'AI triage', detail: 'urgency · category · translation' })
    P.push({ k: 'cluster', kind: 'node', node: 'CP', dur: 0.35, label: 'Geo-cluster', detail: `union-find · eps ${CLUSTER_EPS_M} m` })
    P.push({ k: 'rank', kind: 'node', node: 'CP', dur: 0.2, label: 'Rank', detail: 'urgency + bounded aging' })
    P.push({ k: 'propose', kind: 'node', node: 'CP', dur: 0.5, label: 'Propose responder', detail: 'nearest available · code decides, not the LLM' })
    return P
  }

  /** Appended once a responder is actually assigned — the rest of the loop. */
  buildTailPhases(j) {
    const R = j.responderId
    const P = []
    const taskPath = ['CP', 'G1', 'L1', R]
    const ack = encode({
      id: `${j.sos.origin}-a`,
      type: 'ACCEPTED',
      origin: 'CP01',
      refId: j.sos.id,
      urgency: j.sos.urgency,
      category: j.sos.category,
      locationHint: '',
      gist: 'Help is on the way',
      lang: j.sos.lang,
      ts: j.sos.ts + 6,
      hops: 0,
    })
    j.ackWire = { ...ack, digest: digest(ack.bytes) }
    const ackLora = loraAirtimeMs({ payload: ack.bytes.length })
    j.ackLora = ackLora

    const edge = (from, to, pkt, label, detail) => {
      const kind = linkKind(from, to)
      const dur = kind === 'lora' ? ackLora.airtimeMs / 1000 : kind === 'wire' ? WIRE_S : BLE_S
      return { k: pkt.toLowerCase(), kind: 'edge', from, to, link: kind, pkt, dur, label, detail }
    }

    for (let i = 0; i < taskPath.length - 1; i++) {
      P.push(edge(taskPath[i], taskPath[i + 1], 'TASK', 'Tasking responder', `${this.responders[R].callsign} · ${j.etaMin} min ETA`))
    }
    P.push({ k: 'await', kind: 'node', node: R, dur: 1.3, label: 'Responder decides', detail: 'one tap to accept' })
    for (let i = taskPath.length - 1; i > 0; i--) {
      P.push(edge(taskPath[i], taskPath[i - 1], 'ACCEPT', 'Accepted', 'responder committed'))
    }

    // The return path — this is what makes it a conversation, not a siren.
    const down = [...j.upPath].reverse()
    for (let i = 0; i < down.length - 1; i++) {
      P.push(edge(down[i], down[i + 1], 'ACCEPTED', 'Return path', `ACCEPTED · refId ${j.sos.id} · ${ack.bytes.length} B`))
    }
    P.push({ k: 'delivered', kind: 'node', node: j.vid, dur: 1.4, label: 'Victim hears back', detail: `spoken in ${LANG_NAME[j.sos.lang] ?? j.sos.lang}` })

    if (j.sos.voice) {
      P.push({ k: 'voice', kind: 'voice', dur: 4.6, label: 'Responder pulls the voice clip', detail: 'BLE tier only — gateway skips VoiceChunk on uplink' })
    }

    const compress = this.mode === 'surge' ? this.dayScale : TRAVEL_COMPRESS
    const travel = Math.min(20, Math.max(3, (j.etaMin * 60) / compress))
    const onScene = this.mode === 'surge' ? (ON_SCENE_MIN * 60) / this.dayScale : 1.2

    P.push({ k: 'enroute', kind: 'move', node: R, dur: travel, label: 'Responder en route', detail: `${j.etaMin} min · marker ×${Math.round(compress)} compressed` })
    P.push({ k: 'onscene', kind: 'node', node: j.vid, dur: onScene, label: 'On scene', detail: this.mode === 'surge' ? `≈${ON_SCENE_MIN} min extraction · crew committed` : 'contact made' })
    P.push({ k: 'resolved', kind: 'node', node: j.vid, dur: 0.5, label: 'Resolved', detail: 'crew released to staging' })
    return P
  }

  // --------------------------------------------------------------------- tick
  tick(dt) {
    if (dt <= 0) return

    // In TRACE, once the packets have landed and a responder is walking, there is
    // nothing left to watch at 1×. Warp the clock rather than make the user wait.
    this.warp = 1
    if (this.mode === 'trace') {
      const j = this.journeys[0]
      if (j && !j.done && j.phases[j.pi]?.k === 'enroute') this.warp = 6
    }
    const step = dt * this.warp
    this.clock += step

    while (this.pending.length && this.pending[0].t <= this.clock) {
      this.spawn(this.pending.shift())
    }

    for (const j of this.journeys) this.advance(j, step)
    for (const r of Object.values(this.responders)) this.moveResponder(r, step)

    this.render()

    if (!this.pending.length && this.journeys.every((j) => j.done) && !this.finished) {
      this.finished = true
      this.log(`Scenario complete — ${this.metrics.resolved} incidents resolved, 0 SOS lost.`)
      this.rev++
    }
  }

  advance(j, dt) {
    if (j.done) return
    let guard = 0
    j.pt += dt
    while (j.pi < j.phases.length && j.pt >= j.phases[j.pi].dur && guard++ < 64) {
      const phase = j.phases[j.pi]
      j.pt -= phase.dur
      this.exit(j, phase)
      if (j.repeatPhase) {
        j.repeatPhase = false
        j.pt = 0
        return
      }
      j.pi++
      if (j.pi >= j.phases.length) {
        j.done = true
        j.state = 'resolved'
        this.rev++
        return
      }
      this.enter(j, j.phases[j.pi])
    }
  }

  enter(j, phase) {
    if (phase.kind === 'move') {
      const r = this.responders[j.responderId]
      const inc = this.incidents.get(j.incidentId)
      r.motion = { from: { lat: r.lat, lng: r.lng }, to: { lat: inc.lat, lng: inc.lng }, t: 0, dur: phase.dur, back: false }
      r.status = 'en route'
      inc.state = 'en route'
      j.state = 'responder en route'
      this.log(`${r.callsign} en route to ${inc.id} — ${j.etaMin} min`)
      this.rev++
    }
  }

  exit(j, phase) {
    switch (phase.k) {
      case 'encode':
        this.log(`TX ${j.sos.id} — ${j.wire.bytes.length} B, hash ${j.wire.digest}`)
        this.rev++
        break

      case 'up': {
        if (phase.to === 'CP') {
          this.ingest(j)
        } else {
          j.hops++
        }
        break
      }

      case 'triage': {
        const r = this.incidents.get(j.incidentId)
        this.metrics.triageLatencies.push(j.sos.ai.latencyMs)
        j.state = 'triaged'
        j.triaged = true
        this.log(
          `Triaged ${j.sos.id} — urgency ${j.sos.ai.urgency}/5 · ${j.sos.ai.category} · ${LANG_NAME[j.sos.lang] ?? j.sos.lang} → EN "${j.sos.ai.english}"`,
        )
        if (r) r.state = 'triaged'
        this.rev++
        break
      }

      case 'cluster':
        this.cluster(j)
        break

      case 'rank':
        j.state = 'ranked'
        break

      case 'propose':
        this.propose(j)
        break

      case 'accept': {
        // The last ACCEPT hop lands at the command post.
        if (phase.to === 'CP') {
          const r = this.responders[j.responderId]
          const inc = this.incidents.get(j.incidentId)
          r.status = 'on_task'
          inc.state = 'assigned'
          j.state = 'assigned'
          // Pipeline latency, NOT scaled by the surge day-compression: triage and
          // dispatch take the same few seconds whether or not the scenario clock
          // is compressing 24 h. Only arrival times and queue aging are compressed.
          const decision = this.clock - j.tIngest
          this.metrics.decisionTimes.push(decision)
          this.log(`${r.callsign} accepted ${inc.id} — SOS to dispatch in ${fmt(decision)} s`)
          this.rev++
        }
        break
      }

      case 'delivered':
        this.log(`Victim ${j.sos.origin} heard "Help is on the way" in ${LANG_NAME[j.sos.lang] ?? j.sos.lang}`)
        this.rev++
        break

      case 'voice':
        this.log(`Voice clip ${j.sos.origin}-v0 reassembled at ${this.responders[j.responderId].callsign} — 1 chunk lost, repaired by NACK`)
        this.rev++
        break

      case 'onscene': {
        const inc = this.incidents.get(j.incidentId)
        inc.state = 'on-scene'
        this.rev++
        break
      }

      case 'resolved': {
        const inc = this.incidents.get(j.incidentId)
        const r = this.responders[j.responderId]
        inc.state = 'resolved'
        this.metrics.resolved++
        r.status = 'available'
        r.assignedIncident = null
        r.motion = { from: { lat: r.lat, lng: r.lng }, to: { ...r.base }, t: 0, dur: 8, back: true }
        this.log(`${inc.id} resolved — ${r.callsign} released to staging`)
        this.rev++
        break
      }
      default:
        break
    }
  }

  // ------------------------------------------------------------------- ingest
  ingest(j) {
    j.hops++
    j.tIngest = this.clock
    this.metrics.pktRx++
    this.metrics.bytesRx += j.wire.bytes.length
    j.state = 'received'
    this.log(`RX ${j.sos.id} at command post — ${j.hops} hops, hash ${j.wire.digest} matches TX`)
    this.rev++
  }

  // ---- C1 clustering: split-biased, cluster priority = max member urgency ----
  cluster(j) {
    const v = this.victims[j.vid]
    let target = null

    if (!v.noFix) {
      for (const inc of this.incidents.values()) {
        if (!ACTIVE_STATES.has(inc.state) || inc.noFix) continue
        const km = haversineKm(v.lat, v.lng, inc.lat, inc.lng)
        if (km * 1000 <= CLUSTER_EPS_M) {
          target = inc
          break
        }
      }
    }

    if (target) {
      target.members.push(j.sos.id)
      const before = target.urgency
      target.urgency = Math.max(target.urgency, j.sos.ai.urgency)
      // Cluster != collapse: members keep their own urgency, the incident takes the max.
      target.lat = (target.lat * (target.members.length - 1) + v.lat) / target.members.length
      target.lng = (target.lng * (target.members.length - 1) + v.lng) / target.members.length
      j.incidentId = target.id
      this.log(
        `Clustered ${j.sos.id} into ${target.id} — ${target.members.length} reports within ${CLUSTER_EPS_M} m` +
          (target.urgency > before ? `, incident raised to urgency ${target.urgency}` : ''),
      )
    } else {
      const id = `INC-${String(this.incidents.size + 1).padStart(2, '0')}`
      const inc = {
        id,
        lat: v.lat,
        lng: v.lng,
        noFix: v.noFix,
        hint: j.sos.locationHint,
        urgency: j.sos.ai.urgency,
        category: j.sos.ai.category,
        english: j.sos.ai.english,
        lang: j.sos.lang,
        gist: j.sos.gist,
        members: [j.sos.id],
        state: 'clustered',
        responderId: null,
        createdAt: this.clock,
      }
      this.incidents.set(id, inc)
      j.incidentId = id
      this.log(
        v.noFix
          ? `${id} opened with NO GPS FIX — grouped by relay ${j.relay}, hint "${j.sos.locationHint}". Still triaged, still dispatchable.`
          : `${id} opened — urgency ${inc.urgency}/5 · ${inc.category}`,
      )
    }
    this.rev++
  }

  /** C3 ranking: urgency dominates; aging is bounded so it can never jump a tier. */
  priority(inc) {
    const ageS = (this.clock - inc.createdAt) * this.dayScale
    const boost = AGING_CAP_BOOST * (1 - Math.exp(-ageS / AGING_HALF_LIFE_S))
    return inc.urgency + boost
  }

  // ---- C5 assignment: nearest available responder. Code decides, never the LLM.
  propose(j) {
    const inc = this.incidents.get(j.incidentId)
    if (!inc) return
    if (inc.responderId) {
      // Someone else's report joined an incident already being worked. No second
      // responder is sent — that de-confliction is the point of clustering.
      j.responderId = inc.responderId
      j.etaMin = inc.etaMin ?? 0
      j.state = 'merged into active incident'
      j.phases = j.phases.slice(0, j.pi + 1)
      j.done = true
      this.log(`${j.sos.id} folded into ${inc.id} — ${this.responders[inc.responderId].callsign} already committed, no second crew sent`)
      this.rev++
      return
    }

    const anchor = inc.noFix ? NODES[j.relay] : inc
    const free = Object.values(this.responders).filter((r) => r.status === 'available')

    if (!free.length) {
      if (!j.heldLogged) {
        j.heldLogged = true
        j.state = 'holding'
        inc.state = 'holding'
        this.log(`${inc.id} (urgency ${inc.urgency}) holding — all ${this.crews} crews committed. Ranking decides who goes next.`)
        this.rev++
      }
      j.repeatPhase = true // re-run propose next tick; the queue is doing its job
      return
    }

    // A free crew goes to the highest-ranked waiting incident, not to whichever
    // journey happened to tick first. Without this, "ranked queue" is decoration.
    const contenders = this.journeys.filter((x) => {
      if (x.done || x.phases[x.pi]?.k !== 'propose' || !x.incidentId) return false
      const i = this.incidents.get(x.incidentId)
      return i && !i.responderId
    })
    contenders.sort((a, b) => {
      const ia = this.incidents.get(a.incidentId)
      const ib = this.incidents.get(b.incidentId)
      const d = this.priority(ib) - this.priority(ia)
      return d !== 0 ? d : ia.createdAt - ib.createdAt
    })
    if (contenders.length && contenders[0] !== j) {
      j.repeatPhase = true // someone more urgent is ahead of us
      return
    }

    let best = null
    let bestKm = Infinity
    for (const r of free) {
      const km = haversineKm(anchor.lat, anchor.lng, r.lat, r.lng)
      if (km < bestKm) {
        bestKm = km
        best = r
      }
    }

    j.responderId = best.id
    j.etaMin = Math.max(1, Math.round((bestKm / RESPONDER_SPEED_KMH) * 60))
    best.status = 'proposed'
    best.assignedIncident = inc.id
    inc.responderId = best.id
    inc.state = 'proposed'
    inc.etaMin = j.etaMin
    this.metrics.etaMinutes.push(j.etaMin)
    j.state = 'proposed'
    this.log(`Proposed ${best.callsign} for ${inc.id} — ${fmt(bestKm, 2)} km, ETA ${j.etaMin} min (${best.capability.split('·')[0].trim()})`)
    j.phases = [...j.phases, ...this.buildTailPhases(j)]
    this.rev++
  }

  moveResponder(r, dt) {
    if (!r.motion) return
    r.motion.t += dt
    const u = Math.min(1, r.motion.t / r.motion.dur)
    const e = u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2 // easeInOutQuad
    r.lat = r.motion.from.lat + (r.motion.to.lat - r.motion.from.lat) * e
    r.lng = r.motion.from.lng + (r.motion.to.lng - r.motion.from.lng) * e
    if (u >= 1) {
      const wasBack = r.motion.back
      r.motion = null
      if (wasBack) r.status = 'available'
      else r.status = 'on-scene'
      this.rev++
    }
  }

  // ------------------------------------------------------------------- render
  /** Rebuild the transient visual layers from journey state. Pure derivation. */
  render() {
    const packets = []
    const pulses = []
    const radioTx = []

    for (const j of this.journeys) {
      if (j.done) continue
      const phase = j.phases[j.pi]
      if (!phase) continue
      const t = Math.min(1, j.pt / phase.dur)

      if (phase.kind === 'node') {
        pulses.push({ id: `${j.id}-p`, node: phase.node, k: phase.k, t, urgency: j.sos.ai.urgency })
      } else if (phase.kind === 'edge') {
        // Logical position only — which link, how far along. The view projects.
        packets.push({ id: `${j.id}-${j.pi}`, from: phase.from, to: phase.to, t, pkt: phase.pkt, link: phase.link, urgency: j.sos.ai.urgency, jid: j.id })
        if (phase.link === 'lora') radioTx.push({ node: phase.from, t })
      } else if (phase.kind === 'voice') {
        this.renderVoice(j, packets)
      }
    }

    this.packets = packets
    this.pulses = pulses
    this.radioTx = radioTx
  }

  /**
   * The voice clip, chunk by chunk, on the BLE tier only.
   *
   * A pure function of phase time: chunk 7 dies on its second hop, the responder's
   * phone NACKs the pieces it never got, and the victim's phone resends that chunk
   * with attempt=1 — a different id, so mesh dedup forwards the retry instead of
   * silently dropping it as a duplicate. That `attempt` byte is load-bearing.
   */
  renderVoice(j, packets) {
    const { chunks, loseIndex } = j.sos.voice
    const path = [...j.upPath.slice(0, -2), j.responderId] // drop G1, CP; end at the responder phone
    const nseg = path.length - 1
    const segTotal = nseg * VOICE_HOP_S
    const stagger = 0.24
    const pt = j.pt

    const dieSeg = 1
    const dieAt = dieSeg * VOICE_HOP_S + 0.55 * VOICE_HOP_S
    const nackT = chunks * stagger + segTotal + 0.25
    const resendT = nackT + segTotal + 0.15

    const place = (segIdx, frac, meta) => {
      packets.push({ from: path[segIdx], to: path[segIdx + 1], t: frac, link: 'ble', urgency: 5, jid: j.id, ...meta })
    }

    let arrived = 0
    for (let i = 0; i < chunks; i++) {
      const local = pt - i * stagger
      if (local < 0) continue

      if (i === loseIndex) {
        if (local <= dieAt) {
          const segIdx = Math.min(nseg - 1, Math.floor(local / VOICE_HOP_S))
          place(segIdx, (local % VOICE_HOP_S) / VOICE_HOP_S, { id: `${j.id}-v${i}`, pkt: 'VOICE' })
        } else if (local <= dieAt + 0.5) {
          place(dieSeg, 0.55, { id: `${j.id}-vx`, pkt: 'LOST', dying: (local - dieAt) / 0.5 })
        }
        continue
      }

      if (local <= segTotal) {
        const segIdx = Math.min(nseg - 1, Math.floor(local / VOICE_HOP_S))
        place(segIdx, (local % VOICE_HOP_S) / VOICE_HOP_S, { id: `${j.id}-v${i}`, pkt: 'VOICE' })
      } else {
        arrived++
      }
    }

    // The NACK travels back down the path: origin is the REQUESTER, not the author.
    const nl = pt - nackT
    let repaired = false
    if (nl >= 0 && nl <= segTotal) {
      const segIdx = Math.min(nseg - 1, Math.floor(nl / VOICE_HOP_S))
      const frac = (nl % VOICE_HOP_S) / VOICE_HOP_S
      place(nseg - 1 - segIdx, 1 - frac, { id: `${j.id}-nack`, pkt: 'NACK' })
    }

    const rl = pt - resendT
    if (rl >= 0 && rl <= segTotal) {
      const segIdx = Math.min(nseg - 1, Math.floor(rl / VOICE_HOP_S))
      place(segIdx, (rl % VOICE_HOP_S) / VOICE_HOP_S, { id: `${j.id}-vr`, pkt: 'VOICE', attempt: 1 })
    } else if (rl > segTotal) {
      arrived++
      repaired = true
    }

    j.voiceState = {
      arrived: Math.min(arrived, chunks),
      total: chunks,
      lost: pt > nackT ? 1 : 0,
      repaired,
      nacking: nl >= 0 && nl <= segTotal,
      resending: rl >= 0 && rl <= segTotal,
    }
  }

  // ----------------------------------------------------------------- snapshot
  /** Gateway link health, as surfaced on `/health` (EDGE-LINK.md). */
  gatewayStatus() {
    let queued = 0
    for (const j of this.journeys) {
      if (j.done) continue
      const p = j.phases[j.pi]
      if (p?.kind === 'edge' && (p.pkt === 'SOS' || p.pkt === 'ACK') && (p.link === 'lora' || p.link === 'wire')) queued++
    }
    return { connected: true, queued, lastAckMs: 40 }
  }

  focus() {
    return this.journeys.find((j) => j.id === this.focusId) ?? this.journeys[0] ?? null
  }

  rankedIncidents() {
    return [...this.incidents.values()]
      .map((inc) => ({ ...inc, priority: this.priority(inc) }))
      .sort((a, b) => {
        const aDone = a.state === 'resolved'
        const bDone = b.state === 'resolved'
        if (aDone !== bDone) return aDone ? 1 : -1
        return b.priority - a.priority
      })
  }

  /** Rebuilt every frame: the moving parts. */
  fastSnapshot() {
    return {
      packets: this.packets,
      pulses: this.pulses,
      radioTx: this.radioTx,
      victims: this.victims,
      responders: Object.values(this.responders),
      clock: this.clock,
      warp: this.warp,
      focus: this.focus(),
    }
  }

  slowSnapshot() {
    const m = this.metrics
    const avg = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0)
    return {
      rev: this.rev,
      mode: this.mode,
      crews: this.crews,
      clock: this.clock,
      finished: this.finished,
      incidents: this.rankedIncidents(),
      responders: Object.values(this.responders),
      activity: this.activity,
      gateway: this.gatewayStatus(),
      focus: this.focus(),
      arrived: this.total - this.pending.length,
      total: this.total,
      metrics: {
        pktRx: m.pktRx,
        bytesRx: m.bytesRx,
        resolved: m.resolved,
        open: [...this.incidents.values()].filter((i) => i.state !== 'resolved').length,
        busy: Object.values(this.responders).filter((r) => r.status !== 'available' && r.status !== 'offline').length,
        holding: this.journeys.filter((j) => !j.done && j.state === 'holding').length,
        avgTriageMs: Math.round(avg(m.triageLatencies)),
        avgDecisionS: fmt(avg(m.decisionTimes)),
        avgEtaMin: Math.round(avg(m.etaMinutes)),
      },
    }
  }
}

export const LANG_NAME = { ta: 'Tamil', hi: 'Hindi', ml: 'Malayalam', kn: 'Kannada', en: 'English' }
export { TRAVEL_COMPRESS, CLUSTER_EPS_M }
