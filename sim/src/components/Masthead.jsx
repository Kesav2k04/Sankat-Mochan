import { memo } from 'react'
import { surgeClock } from '../sim/scenario.js'

const SPEEDS = [0.5, 1, 2, 4, 8]

function traceClock(t) {
  const s = Math.floor(t)
  const ms = Math.floor((t - s) * 1000)
  return `T+${String(s).padStart(2, '0')}.${String(ms).padStart(3, '0')}`
}

function Masthead({ mode, clock, warp, running, speed, crews, slow, onMode, onRun, onSpeed, onCrews, onReset }) {
  const { gateway, metrics, arrived, total } = slow
  return (
    <header className="masthead">
      <div className="brand">
        <span className="beacon" />
        <div>
          <h1>Sankat‑Mochan</h1>
          <p>off‑grid rescue mesh · flow simulator</p>
        </div>
      </div>

      <div className="seg modes">
        <button className={mode === 'trace' ? 'on' : ''} onClick={() => onMode('trace')} title="One SOS, every hop, real time">
          Trace
        </button>
        <button className={mode === 'surge' ? 'on' : ''} onClick={() => onMode('surge')} title="40 SOS, 24 hours compressed">
          Surge
        </button>
      </div>

      <div className="clock">
        <b>{mode === 'surge' ? surgeClock(clock) : traceClock(clock)}</b>
        <span>
          {mode === 'surge' ? `${arrived}/${total} SOS` : 'real time'}
          {warp > 1 && ` · ×${warp}`}
        </span>
      </div>

      <div className="transport">
        <button className="play" onClick={() => onRun(!running)} title={running ? 'Pause' : 'Play'}>
          {running ? '❚❚' : '▶'}
        </button>
        <div className="seg">
          {SPEEDS.map((s) => (
            <button key={s} className={speed === s ? 'on' : ''} onClick={() => onSpeed(s)}>
              {s}×
            </button>
          ))}
        </div>
        <div className="seg crews" title="Crews staffed at the relief camp — drop to 2 and watch the queue decide who goes first">
          <span className="seg-label">crews</span>
          {[2, 3, 4].map((c) => (
            <button key={c} className={crews === c ? 'on' : ''} onClick={() => onCrews(c)}>
              {c}
            </button>
          ))}
        </div>
        <button className="reset" onClick={onReset} title="Restart the scenario">
          ↺
        </button>
      </div>

      <div className="stats">
        <Stat label="received" value={metrics.pktRx} />
        <Stat label="open" value={metrics.open} />
        <Stat label="holding" value={metrics.holding} tone={metrics.holding ? 'warn' : ''} />
        <Stat label="resolved" value={metrics.resolved} tone="good" />
        <Stat label="crews busy" value={`${metrics.busy}/${crews}`} tone={metrics.busy === crews ? 'warn' : ''} />
        <div className="gw" title={`gateway link · ${gateway.queued} queued · last ack ${gateway.lastAckMs} ms`}>
          <i className={gateway.connected ? 'ok' : 'bad'} />
          gateway
        </div>
      </div>
    </header>
  )
}

function Stat({ label, value, tone = '' }) {
  return (
    <div className={`stat ${tone}`}>
      <b>{value}</b>
      <span>{label}</span>
    </div>
  )
}

export default memo(Masthead)
