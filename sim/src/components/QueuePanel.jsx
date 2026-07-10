import { memo } from 'react'
import { LANG_NAME } from '../sim/engine.js'

const STATE_TONE = {
  clustered: 'new',
  triaged: 'new',
  holding: 'bad',
  proposed: 'warn',
  assigned: 'warn',
  'en route': 'warn',
  'on-scene': 'cyan',
  resolved: 'good',
}

function QueuePanel({ incidents, responders, onFocus }) {
  const open = incidents.filter((i) => i.state !== 'resolved')
  const done = incidents.filter((i) => i.state === 'resolved')

  return (
    <aside className="queue panel">
      <div className="rail-id">ranked by urgency + bounded aging — a crew goes to #1, not to whoever called last</div>

      <div className="queue-body">
        {!incidents.length && <p className="empty">Nothing triaged yet.</p>}

        {open.map((inc, i) => (
          <button key={inc.id} className="inc" onClick={() => onFocus(inc.members[0])}>
            <div className={`u u${inc.urgency}`}>{inc.urgency}</div>
            <div className="inc-body">
              <div className="inc-top">
                <b>{inc.id}</b>
                <span className="rank">#{i + 1}</span>
                <span className={`state ${STATE_TONE[inc.state] ?? ''}`}>{inc.state}</span>
              </div>
              <p className="inc-en">{inc.english}</p>
              <div className="inc-meta">
                <span>{inc.category}</span>
                <span>{LANG_NAME[inc.lang] ?? inc.lang}</span>
                {inc.members.length > 1 && <span className="merge">{inc.members.length} reports merged</span>}
                {inc.noFix && <span className="nofix">NO GPS · {inc.hint}</span>}
                {inc.etaMin != null && <span className="eta">ETA {inc.etaMin} min</span>}
              </div>
            </div>
          </button>
        ))}

        {done.length > 0 && <div className="queue-sep">RESOLVED · {done.length}</div>}
        {done.map((inc) => (
          <div key={inc.id} className="inc resolved">
            <div className="u done">✓</div>
            <div className="inc-body">
              <div className="inc-top">
                <b>{inc.id}</b>
                <span className="state good">resolved</span>
              </div>
              <p className="inc-en">{inc.english}</p>
            </div>
          </div>
        ))}
      </div>

      <h2 className="sub-h">Responders</h2>
      <div className="responders">
        {responders.map((r) => (
          <div key={r.id} className={`resp ${r.status.replace(/[ _]/g, '-')}`}>
            <div className="resp-top">
              <b>{r.callsign}</b>
              <span>{r.status.replace('_', ' ')}</span>
            </div>
            <p>{r.capability}</p>
            {r.assignedIncident && <div className="resp-task">→ {r.assignedIncident}</div>}
          </div>
        ))}
      </div>
    </aside>
  )
}

export default memo(QueuePanel)
