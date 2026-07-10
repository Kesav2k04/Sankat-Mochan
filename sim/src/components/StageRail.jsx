const GROUP = {
  speak: 'CAPTURE',
  stt: 'CAPTURE',
  encode: 'CAPTURE',
  up: 'MESH TRANSPORT',
  ack: 'MESH TRANSPORT',
  triage: 'OFFLINE AI',
  cluster: 'OFFLINE AI',
  rank: 'OFFLINE AI',
  propose: 'OFFLINE AI',
  task: 'DISPATCH',
  await: 'DISPATCH',
  accept: 'DISPATCH',
  accepted: 'RETURN PATH',
  delivered: 'RETURN PATH',
  voice: 'RETURN PATH',
  enroute: 'FIELD',
  onscene: 'FIELD',
  resolved: 'FIELD',
}

const LINK_TAG = { ble: 'BLE', lora: 'LoRa', wire: 'ETH' }

export default function StageRail({ focus }) {
  if (!focus) {
    return (
      <aside className="rail panel">
        <p className="empty">Waiting for the first SOS…</p>
      </aside>
    )
  }

  let lastGroup = null
  return (
    <aside className="rail panel">
      <div className="rail-id">
        following <b>{focus.id}</b> — click any victim on the map to switch
      </div>
      <div className="rail-body">
        {focus.phases.map((p, i) => {
          const state = i < focus.pi ? 'done' : i === focus.pi ? 'active' : 'todo'
          const group = GROUP[p.k] ?? '—'
          const header = group !== lastGroup ? group : null
          lastGroup = group
          const pct = state === 'active' ? Math.min(100, (focus.pt / p.dur) * 100) : state === 'done' ? 100 : 0
          return (
            <div key={i}>
              {header && <div className="rail-group">{header}</div>}
              <div className={`step ${state}`}>
                <div className="tick">{state === 'done' ? '✓' : state === 'active' ? '●' : '○'}</div>
                <div className="step-body">
                  <div className="step-top">
                    <span className="step-label">{p.label}</span>
                    {p.kind === 'edge' && <span className={`tag ${p.link}`}>{LINK_TAG[p.link]}</span>}
                    <span className="step-dur">{p.dur < 1 ? `${Math.round(p.dur * 1000)} ms` : `${p.dur.toFixed(1)} s`}</span>
                  </div>
                  <div className="step-detail">{p.detail}</div>
                  <div className="step-bar">
                    <i style={{ width: `${pct}%` }} />
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </aside>
  )
}
