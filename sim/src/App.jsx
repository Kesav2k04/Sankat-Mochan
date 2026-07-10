import { useCallback, useEffect, useRef, useState } from 'react'
import { Sim } from './sim/engine.js'
import Masthead from './components/Masthead.jsx'
import MeshTheatre from './components/MeshTheatre.jsx'
import StageRail from './components/StageRail.jsx'
import QueuePanel from './components/QueuePanel.jsx'
import Inspector from './components/Inspector.jsx'
import ActivityLog from './components/ActivityLog.jsx'

const MAX_STEP = 0.05 // never advance more than 50 ms of sim per frame

const TABS = [
  { id: 'flow', label: 'Journey' },
  { id: 'queue', label: 'Queue' },
  { id: 'packet', label: 'Packet' },
]

export default function App() {
  const ref = useRef(null)
  if (!ref.current) ref.current = new Sim()
  const engine = ref.current

  const [mode, setMode] = useState('trace')
  const [running, setRunning] = useState(true)
  const [speed, setSpeed] = useState(1)
  const [crews, setCrews] = useState(4)
  const [tab, setTab] = useState('flow')
  const [fast, setFast] = useState(() => engine.fastSnapshot())
  const [slow, setSlow] = useState(() => engine.slowSnapshot())

  // The rAF loop reads these without re-subscribing.
  const cfg = useRef({ running, speed })
  cfg.current = { running, speed }
  const lastRev = useRef(-1)

  useEffect(() => {
    let raf = 0
    let prev = performance.now()
    const loop = (now) => {
      const dt = Math.min(MAX_STEP, (now - prev) / 1000)
      prev = now
      if (cfg.current.running) engine.tick(dt * cfg.current.speed)
      setFast(engine.fastSnapshot())
      if (engine.rev !== lastRev.current) {
        lastRev.current = engine.rev
        setSlow(engine.slowSnapshot())
      }
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [engine])

  const restart = useCallback(
    (m, c) => {
      engine.reset(m, c)
      lastRev.current = -1
      setSpeed(m === 'surge' ? 2 : 1)
      setRunning(true)
      setFast(engine.fastSnapshot())
      setSlow(engine.slowSnapshot())
    },
    [engine],
  )

  const onMode = useCallback(
    (m) => {
      setMode(m)
      setTab(m === 'surge' ? 'queue' : 'flow') // each mode opens on its natural view
      restart(m, crews)
    },
    [restart, crews],
  )

  const onCrews = useCallback(
    (c) => {
      setCrews(c)
      restart(mode, c)
    },
    [restart, mode],
  )

  const onFocus = useCallback(
    (id) => {
      engine.focusId = id
      engine.rev++
    },
    [engine],
  )

  return (
    <div className="app">
      <Masthead
        mode={mode}
        clock={fast.clock}
        warp={fast.warp}
        running={running}
        speed={speed}
        crews={crews}
        slow={slow}
        onMode={onMode}
        onRun={setRunning}
        onSpeed={setSpeed}
        onCrews={onCrews}
        onReset={() => restart(mode, crews)}
      />

      <main>
        <div className="stage-card">
          <MeshTheatre fast={fast} incidents={slow.incidents} focusId={engine.focusId} onFocus={onFocus} />
        </div>

        <aside className="rail-card">
          <nav className="tabs">
            {TABS.map((t) => (
              <button key={t.id} className={tab === t.id ? 'on' : ''} onClick={() => setTab(t.id)}>
                {t.label}
              </button>
            ))}
          </nav>
          <div className="rail-content">
            {tab === 'flow' && <StageRail focus={fast.focus} />}
            {tab === 'queue' && <QueuePanel incidents={slow.incidents} responders={slow.responders} onFocus={onFocus} />}
            {tab === 'packet' && <Inspector focus={fast.focus} />}
          </div>
        </aside>
      </main>

      <ActivityLog activity={slow.activity} />

      {slow.finished && (
        <div className="finished">
          <b>Scenario complete</b>
          <span>
            {slow.metrics.pktRx} SOS received · {slow.metrics.resolved} resolved · 0 lost — no tower, no internet
          </span>
        </div>
      )}
    </div>
  )
}
