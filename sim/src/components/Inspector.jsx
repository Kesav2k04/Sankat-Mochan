import { hexdump, MAX_BYTES, LORA_RADIO } from '../sim/envelope.js'
import { LANG_NAME } from '../sim/engine.js'

function Bytes({ bytes }) {
  const rows = hexdump(bytes, 8)
  return (
    <div className="hex">
      {rows.map((r) => (
        <div key={r.off} className="hex-row">
          <span className="off">{r.off}</span>
          <span className="cells">
            {r.hex.map((h, i) => (
              <b key={i}>{h}</b>
            ))}
          </span>
          <span className="ascii">{r.ascii}</span>
        </div>
      ))}
    </div>
  )
}

export default function Inspector({ focus }) {
  if (!focus) {
    return (
      <section className="inspector panel">
        <p className="empty">No packet in flight yet.</p>
      </section>
    )
  }

  const { wire, sos, lora } = focus
  const pct = (wire.bytes.length / MAX_BYTES) * 100
  const vs = focus.voiceState

  return (
    <section className="inspector panel">
      <div className="card">
        <div className="card-head">
          <h3>Envelope · {sos.id}</h3>
          <span className={`pill u${sos.ai.urgency}`}>urgency {sos.ai.urgency}/5</span>
        </div>

        <div className="budget">
          <div className="budget-bar">
            <i style={{ width: `${pct}%` }} className={pct > 92 ? 'tight' : ''} />
          </div>
          <span>
            {wire.bytes.length} / {MAX_BYTES} B{wire.trimmed > 0 && <em> · trimmed {wire.trimmed} chars</em>}
          </span>
        </div>

        <div className="translation">
          <div>
            <span>victim said · {LANG_NAME[sos.lang] ?? sos.lang}</span>
            {/* Untrusted free text — React escapes it; never inserted as HTML. */}
            <p lang={sos.lang}>{sos.gist}</p>
          </div>
          <div>
            <span>offline AI translated</span>
            <p className={focus.triaged ? 'en' : 'en pending'}>{focus.triaged ? sos.ai.english : '…'}</p>
          </div>
        </div>

        <div className="kv">
          <div><span>hash TX</span><b>{wire.digest}</b></div>
          <div><span>hash RX</span><b className={focus.tIngest ? 'good' : 'dim'}>{focus.tIngest ? wire.digest : '—'}</b></div>
          <div><span>hops</span><b>{focus.hops}</b></div>
          <div><span>category</span><b>{sos.ai.category}</b></div>
        </div>

        <details>
          <summary>Wire bytes — what actually crosses the air</summary>
          <pre className="json">{wire.json}</pre>
          <Bytes bytes={wire.bytes.slice(0, 48)} />
        </details>
      </div>

      <div className="card">
        <div className="card-head">
          <h3>LoRa hop · L1 → gateway</h3>
          <span className="pill amber">{LORA_RADIO.band}</span>
        </div>
        <div className="kv">
          <div><span>radio</span><b>SF{LORA_RADIO.sf} · {LORA_RADIO.bwKHz} kHz · {LORA_RADIO.crLabel}</b></div>
          <div><span>frequency</span><b>{LORA_RADIO.freqMHz} MHz</b></div>
          <div><span>bitrate</span><b>{Math.round(lora.bitrateBps)} bps</b></div>
          <div><span>time on air</span><b className="big">{lora.airtimeMs.toFixed(0)} ms</b></div>
        </div>
        <p className="note">
          Computed from the Semtech airtime formula, not typed in. One 237‑byte envelope occupies the channel for over a
          second — which is exactly why voice never rides this link.
        </p>
        {focus.ackWire && (
          <div className="kv">
            <div>
              <span>return path · ACCEPTED</span>
              <b>{focus.ackWire.bytes.length} B · {focus.ackLora.airtimeMs.toFixed(0)} ms</b>
            </div>
          </div>
        )}
      </div>

      {sos.voice && (
        <div className="card">
          <div className="card-head">
            <h3>Voice clip · BLE tier only</h3>
            <span className="pill cyan">ogg/opus</span>
          </div>
          <div className="kv">
            <div><span>reassembled</span><b>{vs?.arrived ?? 0}/{sos.voice.chunks} chunks</b></div>
            <div><span>lost</span><b className={vs?.lost && !vs?.repaired ? 'bad' : ''}>{vs?.repaired ? 'repaired' : vs?.lost ?? 0}</b></div>
            <div><span>state</span><b>{vs?.nacking ? 'NACK in flight' : vs?.resending ? 'resending #1' : vs?.repaired ? 'complete' : 'waiting'}</b></div>
          </div>
          <p className="note">
            A lost chunk is re‑requested by NACK and resent with <code>attempt=1</code> — a different id, so mesh dedup
            forwards the retry instead of dropping it as a duplicate. The gateway skips voice on uplink; audio stays on
            the phone tier.
          </p>
        </div>
      )}
    </section>
  )
}
