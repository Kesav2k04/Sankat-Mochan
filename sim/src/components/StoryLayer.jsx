import { useState } from 'react'
import phonePng from '../assets/phone.png'
import { SCENES } from './scenes.jsx'

/**
 * The story overlays that sit ON TOP of the live map: film-style captions,
 * chapter dots, and — at the final beat — the victim's actual phone screen,
 * where tapping the real SOS card is what launches the simulation.
 */
export default function StoryLayer({ beats, beat, onNext, onJump, onSkip, onSos }) {
  const BEATS = beats
  const b = BEATS[beat]
  if (!b) return null

  return (
    <>
      <button className="cine-skip" onClick={onSkip}>
        Skip story →
      </button>

      <div className={`cine-caption ${b.phone ? 'left' : ''}`} key={beat} onClick={() => !b.phone && onNext()}>
        {SCENES[b.key] && <div className="cine-scene">{SCENES[b.key]}</div>}
        <div className="cine-copy">
          <span className="cine-hour">{b.hour}</span>
          <b>{b.title}</b>
          <p>{b.text}</p>
          {!b.phone && <span className="cine-hint">click to continue</span>}
        </div>
      </div>

      <div className="cine-dots">
        {BEATS.map((x, k) => (
          <button key={k} className={k === beat ? 'on' : k < beat ? 'done' : ''} onClick={() => onJump(k)}>
            {k === beat && x.dur && <i style={{ animationDuration: `${x.dur}s` }} />}
          </button>
        ))}
      </div>

      {b.phone && <PhonePanel onSos={onSos} />}
    </>
  )
}

function PhonePanel({ onSos }) {
  const [sent, setSent] = useState(false)
  const press = () => {
    if (sent) return
    setSent(true)
    setTimeout(onSos, 1100) // let "SOS SENT" land before the mesh takes over
  }
  return (
    <div className="phone-panel">
      <div className={`phone-shell ${sent ? 'sent' : ''}`}>
        <img src={phonePng} alt="Sankat-Mochan — Send for help" draggable="false" />
        {/* the red SOS card region of the screenshot */}
        <button className="phone-tap" onClick={press} disabled={sent} aria-label="Press SOS">
          {!sent && (
            <span className="tap-ring">
              <i />
              TAP SOS
            </span>
          )}
        </button>
        {sent && <div className="phone-sent">SOS SENT — riding the mesh</div>}
      </div>
    </div>
  )
}
