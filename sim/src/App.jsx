import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import SimMap from './components/SimMap.jsx'
import Story from './components/Story.jsx'
import StoryLayer from './components/StoryLayer.jsx'
import Lottie from './components/Lottie.jsx'
import aiRobot from './assets/ai-robot.json'
import { BEATS } from './sim/story.js'

/** After the full-screen chapters, only these beats continue ON the map. */
const MAP_BEATS = BEATS.filter((b) => b.mesh || b.phone)
import { autoLayout, MAX_NODES, RANGE_KM, bestOrigin, buildLinks, buildTimeline, inZone, placeRangers } from './sim/lora.js'

export default function App() {
  const [screenStory, setScreenStory] = useState(true) // the animated full-screen chapters
  const [story, setStory] = useState({ on: false, beat: 0 }) // then the on-map beats
  const [towerDown, setTowerDown] = useState(false)
  const [scarSeen, setScarSeen] = useState(false)
  const [phase, setPhase] = useState('setup') // setup -> run -> done
  const [nodes, setNodes] = useState([])
  const [run, setRun] = useState(null)
  const [clock, setClock] = useState(0)
  const [hint, setHint] = useState('')

  const layoutRef = useRef(null) // one layout per story session, so beats and skip agree
  const storyRef = useRef(story)
  storyRef.current = story

  const beat = story.on ? MAP_BEATS[story.beat] : null

  const links = useMemo(() => buildLinks(nodes), [nodes])
  const best = useMemo(() => (nodes.length ? bestOrigin(nodes) : { heard: 0, path: null }), [nodes])
  const spotCovered = best.heard > 0
  const path = best.path
  const rangers = useMemo(() => (run ? run.rangers : path ? placeRangers(path) : []), [run, path])
  const canStart = phase === 'setup' && !!path

  // ---- story direction (the on-map beats) -----------------------------------
  useEffect(() => {
    if (!story.on) return
    const b = MAP_BEATS[story.beat]
    if (!b || b.dur == null) return
    const t = setTimeout(() => setStory((s) => ({ ...s, beat: Math.min(s.beat + 1, MAP_BEATS.length - 1) })), b.dur * 1000)
    return () => clearTimeout(t)
  }, [story])

  // the full-screen chapters hand over to the map: the scars of the night are
  // already on the ground, then the mesh wakes and the victim reaches for the phone
  const screenStoryDone = () => {
    setScreenStory(false)
    setTowerDown(true)
    setScarSeen(true)
    setStory({ on: true, beat: 0 })
  }

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
    setRun(t)
    setClock(0)
    setPhase('run')
  }, [nodes])

  const skipStory = () => {
    layoutRef.current ??= autoLayout()
    setNodes(layoutRef.current)
    setTowerDown(true)
    setScarSeen(true)
    setScreenStory(false)
    setStory({ on: false, beat: 0 })
  }

  const onSos = () => {
    setStory({ on: false, beat: 0 })
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
    setStory({ on: false, beat: 0 })
    setScreenStory(true)
  }

  const reset = () => {
    setRun(null)
    setClock(0)
    setPhase('setup')
  }

  const events = run ? run.events.filter((e) => e.t <= clock).slice(-6) : []

  return (
    <div className="app">
      {screenStory && <Story onDone={screenStoryDone} onSkip={skipStory} />}
      <header className="masthead">
        <div className="brand">
          <span className="beacon" />
          <div>
            <h1>Sankat‑Mochan</h1>
            <p>LoRa SOS relay · Wayanad, Kerala</p>
          </div>
        </div>

        <div className="clock">
          <b>{story.on ? MAP_BEATS[story.beat].hour.split('·')[0].trim() : phase === 'setup' ? '—' : `T+${clock.toFixed(1)}s`}</b>
          <span>{screenStory || story.on ? 'the night of the disaster' : phase === 'setup' ? 'placing modules' : phase === 'run' ? 'live' : 'complete'}</span>
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
          phase={story.on ? 'story' : phase}
          nodes={nodes}
          links={links}
          path={path}
          rangers={rangers}
          run={run}
          clock={clock}
          fx={beat?.fx ?? null}
          beatKey={beat?.key ?? null}
          showZone={!story.on || !!beat?.zone}
          showTower={towerDown}
          showScar={scarSeen}
          storyVictim={!!beat?.phone}
          onPlace={place}
        />

        {story.on && (
          <StoryLayer
            beats={MAP_BEATS}
            beat={story.beat}
            onNext={() => setStory((s) => ({ ...s, beat: Math.min(s.beat + 1, MAP_BEATS.length - 1) }))}
            onJump={(k) => setStory((s) => ({ ...s, beat: k }))}
            onSkip={skipStory}
            onSos={onSos}
          />
        )}

        {!story.on && phase === 'setup' && (
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
          <div className="finished">
            <b>Rescue loop closed</b>
            <span>
              camp received in {run.outpostAt.toFixed(1)} s ({run.hops} hops) · supplies suggested from the voice note · ranger tasked, accepted, and on scene · victim told help is coming — no tower, no internet
            </span>
          </div>
        )}
      </main>
    </div>
  )
}
