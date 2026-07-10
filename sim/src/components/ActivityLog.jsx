import { memo, useState } from 'react'

/**
 * The C13 audit log, folded into a one-line ticker. The latest decision scrolls
 * past at the bottom; the full append-only history is one click away.
 */
function ActivityLog({ activity }) {
  const [open, setOpen] = useState(false)
  const latest = activity[0]

  return (
    <div className={`activity ${open ? 'open' : ''}`}>
      {open && (
        <div className="log-sheet">
          {activity.map((a) => (
            <div key={a.id} className={`row ${tone(a.text)}`}>
              <span className="t">{stamp(a.ts)}</span>
              <span className="msg">{a.text}</span>
            </div>
          ))}
        </div>
      )}
      <button className="ticker" onClick={() => setOpen(!open)} title="Every automated decision, with its reason">
        <span className="ticker-label">activity</span>
        <span className={`ticker-msg ${latest ? tone(latest.text) : ''}`}>{latest ? latest.text : '—'}</span>
        <span className="ticker-count">
          {activity.length} · {open ? '▾' : '▴'}
        </span>
      </button>
    </div>
  )
}

function stamp(t) {
  const s = Math.floor(t)
  const cs = Math.floor((t - s) * 100)
  return `${String(s).padStart(3, '0')}.${String(cs).padStart(2, '0')}`
}

function tone(text) {
  // Order matters: "Scenario complete — … 0 SOS lost" must not read as a warning.
  if (/Scenario complete/.test(text)) return 'good'
  if (/holding|NO GPS|lost/i.test(text)) return 'warn'
  if (/resolved|accepted|heard/i.test(text)) return 'good'
  if (/Triaged|Clustered|Proposed|folded/i.test(text)) return 'ai'
  return ''
}

export default memo(ActivityLog)
