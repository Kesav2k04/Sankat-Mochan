import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import SimMap from './components/SimMap.jsx'
import StoryLayer from './components/StoryLayer.jsx'
import Lottie from './components/Lottie.jsx'
import aiRobot from './assets/ai-robot.json'
import { BEATS } from './sim/story.js'
import savedAnim from './assets/saved.json'
import { autoLayout, MAX_NODES, OUTPOST, RANGE_KM, bestOrigin, buildLinks, buildTimeline, inZone, placeRangers } from './sim/lora.js'

function easeInOut(u) {
  return u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2
}

/**
 * What the camera should be looking at right now: the packet in flight, the
 * camp while it thinks, the ranger while they decide and travel, and finally
 * the victim. One continuous shot from the SOS tap to the rescue.
 */
function followTarget(run, clock) {
  const resp = run.segs.find((s) => s.kind === 'respond')
  if (resp && clock >= resp.t0) {
    const u = easeInOut(Math.min(1, (clock - resp.t0) / resp.dur))
    if (u >= 1) return { lat: run.victim.lat, lng: run.victim.lng, zoom: 12.8 }
    return { lat: resp.from.lat + (resp.to.lat - resp.from.lat) * u, lng: resp.from.lng + (resp.to.lng - resp.from.lng) * u, zoom: 12.2 }
  }
  const hops = run.segs.filter((s) => s.kind === 'hop')
  const active = [...hops].reverse().find((s) => clock >= s.t0 && clock <= s.t0 + s.dur)
  if (active) {
    // ride ON the dot — tight zoom so you watch it travel hop by hop
    const u = Math.min(1, (clock - active.t0) / active.dur)
    return { lat: active.from.lat + (active.to.lat - active.from.lat) * u, lng: active.from.lng + (active.to.lng - active.from.lng) * u, zoom: 13.3 }
  }
  // the quiet moments between signals
  if (clock < (hops[0]?.t0 ?? 0)) return { lat: run.victim.lat, lng: run.victim.lng, zoom: 12.8 } // speaking
  if (clock >= run.task.tAlert && clock < run.task.tAccept + 0.4) {
    const r = run.rangers.find((x) => x.id === run.task.rid)
    return { lat: r.lat, lng: r.lng, zoom: 12.9 } // the ranger, deciding
  }
  return { lat: OUTPOST.lat, lng: OUTPOST.lng, zoom: 12.8 } // the camp, thinking
}

const WIDE = [
  [76.0, 11.57],
  [76.27, 11.8],
]

export default function App() {
  const [story, setStory] = useState({ on: true, beat: 0 }) // the whole story lives on the map
  const [towerDown, setTowerDown] = useState(false)
  const [scarSeen, setScarSeen] = useState(false)
  const [phase, setPhase] = useState('setup') // setup -> run -> done
  const [nodes, setNodes] = useState([])
  const [run, setRun] = useState(null)
  const [clock, setClock] = useState(0)
  const [hint, setHint] = useState('')

  const layoutRef = useRef(null) // one layout per story session, so beats and skip agree
  const mapApi = useRef(null)
  const [mapReady, setMapReady] = useState(false)
  const storyRef = useRef(story)
  storyRef.current = story

  const inStory = story.on
  const beat = story.on ? BEATS[story.beat] : null

  const links = useMemo(() => buildLinks(nodes), [nodes])
  const best = useMemo(() => (nodes.length ? bestOrigin(nodes) : { heard: 0, path: null }), [nodes])
  const spotCovered = best.heard > 0
  const path = best.path
  const rangers = useMemo(() => (run ? run.rangers : path ? placeRangers(path) : []), [run, path])
  const canStart = phase === 'setup' && !!path

  // ---- story direction — each beat plays on the map, then hands to the next --
  useEffect(() => {
    if (!story.on) return
    const b = BEATS[story.beat]
    if (!b || b.dur == null) return
    const t = setTimeout(() => setStory((s) => ({ ...s, beat: Math.min(s.beat + 1, BEATS.length - 1) })), b.dur * 1000)
    return () => clearTimeout(t)
  }, [story])

  // the camera dives into each beat: the sliding rock, the dead tower, the
  // waking mesh, the victim. Safe now — the overlay re-projects on every move.
  useEffect(() => {
    if (!story.on || !mapReady) return
    const b = BEATS[story.beat]
    if (b?.cam) mapApi.current?.easeTo({ center: b.cam.center, zoom: b.cam.zoom, duration: 1800 })
  }, [story, mapReady])

  // the tower stays broken and the scar stays scarred once the story shows them
  useEffect(() => {
    if (beat?.tower) setTowerDown(true)
    if (beat?.scar) setScarSeen(true)
  }, [beat])

  // "the mesh wakes up" — modules pop onto the map one by one
  useEffect(() => {
    if (!beat?.mesh) return
    layoutRef.current ??= autoLayout()
    const layout = layoutRef.current
    const iv = setInterval(() => {
      setNodes((ns) => (ns.length >= layout.length ? ns : layout.slice(0, ns.length + 1)))
    }, 330)
    return () => clearInterval(iv)
  }, [beat])

  // ---- run clock ------------------------------------------------------------
  useEffect(() => {
    if (phase !== 'run') return
    let raf = 0
    let prev = performance.now()
    const loop = (now) => {
      const dt = Math.min(0.05, (now - prev) / 1000)
      prev = now
      setClock((c) => c + dt)
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [phase])

  useEffect(() => {
    if (phase === 'run' && run && clock >= run.total) setPhase('done')
  }, [phase, run, clock])

  // the follow shot: every frame, glide the camera toward whatever carries the
  // story right now — the signal, the camp, the ranger, the victim
  const camPos = useRef(null)
  useEffect(() => {
    if (phase !== 'run' || !run || !mapReady) return
    const m = mapApi.current
    if (!m) return
    const t = followTarget(run, clock)
    if (!camPos.current) {
      const c = m.getCenter()
      camPos.current = { lat: c.lat, lng: c.lng, zoom: m.getZoom() }
    }
    const p = camPos.current
    // tight tracking: at this zoom the dot must stay in the frame
    p.lat += (t.lat - p.lat) * 0.11
    p.lng += (t.lng - p.lng) * 0.11
    p.zoom += (t.zoom - p.zoom) * 0.06
    m.jumpTo({ center: [p.lng, p.lat], zoom: p.zoom })
  }, [clock, phase, run, mapReady])

  // ---- actions --------------------------------------------------------------
  const place = useCallback((p) => {
    if (storyRef.current.on) return // the story owns the map until it ends
    if (!inZone(p)) {
      setHint('Modules must be INSIDE the danger zone.')
      return
    }
    setHint('')
    setNodes((ns) => (ns.length >= MAX_NODES ? ns : [...ns, p]))
  }, [])

  const start = useCallback(() => {
    const t = buildTimeline(layoutRef.current && !nodes.length ? layoutRef.current : nodes)
    if (!t) return
    camPos.current = null
    setRun(t)
    setClock(0)
    setPhase('run')
  }, [nodes])

  const skipStory = () => {
    layoutRef.current ??= autoLayout()
    setNodes(layoutRef.current)
    setTowerDown(true)
    setScarSeen(true)
    setStory({ on: false, beat: 0 })
    mapApi.current?.fitBounds(WIDE, { padding: 24, duration: 1200 })
  }

  const onSos = () => {
    setStory({ on: false, beat: 0 })
    camPos.current = null // the follow shot picks up from wherever we are
    start()
  }

  const replayStory = () => {
    setRun(null)
    setClock(0)
    setPhase('setup')
    setNodes([])
    setTowerDown(false)
    setScarSeen(false)
    layoutRef.current = null
    setStory({ on: true, beat: 0 })
  }

  const reset = () => {
    setRun(null)
    setClock(0)
    setPhase('setup')
    camPos.current = null
    mapApi.current?.fitBounds(WIDE, { padding: 24, duration: 1200 })
  }

  const events = run ? run.events.filter((e) => e.t <= clock).slice(-6) : []

  return (
    <div className="app">
      <header className="masthead">
        <div className="brand">
          <span className="beacon" />
          <div>
            <h1>Sankat‑Mochan</h1>
            <p>LoRa SOS relay · Wayanad, Kerala</p>
          </div>
        </div>

        <div className="clock">
          <b>{story.on ? BEATS[story.beat].hour.split('·')[0].trim() : phase === 'setup' ? '—' : `T+${clock.toFixed(1)}s`}</b>
          <span>{story.on ? 'the night of the disaster' : phase === 'setup' ? 'placing modules' : phase === 'run' ? 'live' : 'complete'}</span>
        </div>

        <div className="controls">
          <button className="ghost" onClick={replayStory} title="Replay the story">
            ✦ Story
          </button>
          {!story.on &&
            (phase === 'setup' ? (
              <>
                <button className="ghost" onClick={() => { setNodes(autoLayout()); setHint('') }}>
                  Auto‑place
                </button>
                <button className="ghost" onClick={() => { setNodes([]); setHint('') }} disabled={!nodes.length}>
                  Clear
                </button>
                <button className="primary" onClick={start} disabled={!canStart}>
                  ▶ Simulate
                </button>
              </>
            ) : (
              <button className="primary" onClick={reset}>↺ Reset</button>
            ))}
        </div>
      </header>

      <main>
        <SimMap
          phase={inStory ? 'story' : phase}
          nodes={nodes}
          links={links}
          path={path}
          rangers={rangers}
          run={run}
          clock={clock}
          fx={beat?.fx ?? null}
          beatKey={beat?.key ?? null}
          showZone={!inStory || !!beat?.zone}
          showTower={towerDown}
          showScar={scarSeen}
          storyVictim={!!beat?.phone}
          onPlace={place}
          onReady={(m) => {
            mapApi.current = m
            setMapReady(true)
          }}
        />

        {story.on && (
          <StoryLayer
            beats={BEATS}
            beat={story.beat}
            onNext={() => setStory((s) => ({ ...s, beat: Math.min(s.beat + 1, BEATS.length - 1) }))}
            onJump={(k) => setStory((s) => ({ ...s, beat: k }))}
            onSkip={skipStory}
            onSos={onSos}
          />
        )}

        {!inStory && phase === 'setup' && (
          <div className="setup-card">
            <b>Set up the mesh</b>
            <p>
              The SOS will come from the <em>danger spot</em> (⚠ deep in the zone). Click inside the red zone to drop
              LoRa modules ({nodes.length}/{MAX_NODES}) — each reaches ~{RANGE_KM} km. Chain them from the spot to the
              outpost, or use <em>Auto‑place</em>.
            </p>
            {hint && <p className="warn">{hint}</p>}
            {nodes.length > 0 && !spotCovered && <p className="warn">No module within {RANGE_KM} km of the danger spot yet — surround the spot first.</p>}
            {nodes.length > 0 && spotCovered && !path && <p className="warn">Chain doesn’t reach the outpost yet — add a module closer to it.</p>}
            {path && (
              <p className="ok">
                {best.heard} module{best.heard > 1 ? 's' : ''} cover the spot · shortest route: {path.length - 1} hops to the camp. Ready.
              </p>
            )}
          </div>
        )}

        {/* what the safe camp does with the SOS: transcribe -> triage -> supplies */}
        {run && clock >= run.triage.t && (
          <div className="triage-card">
            <div className="tr-head">
              <Lottie data={aiRobot} className="tr-lottie" />
              <b>SAFE CAMP · offline AI triage</b>
            </div>
            <p className="tr">“{run.triage.transcript}”</p>
            <div className="tr-meta">
              urgency <em>{run.triage.urgency}/5</em> · {run.triage.category} · from {run.triage.lang} voice note
            </div>
            <div className="chips">
              {run.triage.supplies.map((s) => (
                <span key={s}>{s}</span>
              ))}
            </div>
            {clock >= run.dispatchAt && <p className="tr-dispatch">→ nearest ranger tasked with this list, over the same mesh</p>}
          </div>
        )}

        {events.length > 0 && (
          <div className="events">
            {events.map((e, i) => (
              <div key={`${e.t}-${i}`} className={`ev ${e.tone ?? ''}`}>
                <span>{e.t.toFixed(1)}s</span>
                {e.text}
              </div>
            ))}
          </div>
        )}

        {phase === 'done' && (
          <div className="saved-pop">
            <Lottie data={savedAnim} className="saved-lottie" />
            <b>VICTIM SAVED</b>
            <p>
              SOS reached the camp in {run.outpostAt.toFixed(1)} s over {run.hops} LoRa hops · supplies suggested from the
              voice note · ranger tasked, accepted, on scene — no tower, no internet.
            </p>
            <div className="saved-actions">
              <button className="ghost" onClick={replayStory}>✦ Replay the story</button>
              <button className="primary" onClick={reset}>↺ Run again</button>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
