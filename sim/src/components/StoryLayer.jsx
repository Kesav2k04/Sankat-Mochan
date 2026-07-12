import { useState } from 'react'
import phonePng from '../assets/phone.png'
import { SCENES } from './scenes.jsx'

/**
 * The cinema layer that sits ON TOP of the live map: letterbox bars, the big
 * illustrated scene panel, film-style lower-third titles, chapter progress —
 * and, at the final beat, the victim's actual phone screen, where tapping the
 * real SOS card is what launches the simulation.
 */
export default function StoryLayer({ beats, beat, onNext, onJump, onSkip, onSos }) {
  const b = beats[beat]
  if (!b) return null
  const clickable = !b.phone

  return (
    <div className="cine" onClick={() => clickable && onNext()}>
      {/* letterbox bars own the frame */}
      <div className="cine-bar top">
        <span className="cine-reel">SANKAT‑MOCHAN · A NIGHT IN WAYANAD</span>
        <button
          className="cine-skip"
          onClick={(e) => {
            e.stopPropagation()
            onSkip()
          }}
        >
          SKIP ▸
        </button>
      </div>
      <div className="cine-bar bottom">
        <div className="cine-dots" onClick={(e) => e.stopPropagation()}>
          {beats.map((x, k) => (
            <button key={k} className={k === beat ? 'on' : k < beat ? 'done' : ''} onClick={() => onJump(k)} aria-label={x.title}>
              {k === beat && x.dur && <i style={{ animationDuration: `${x.dur}s` }} />}
            </button>
          ))}
        </div>
      </div>

      {/* the big illustrated shot — remounts every beat so its film plays once */}
      {b.scene === 'hero' && SCENES[b.key] && (
        <div className="cine-hero" key={`hero-${beat}`}>
          {SCENES[b.key]}
        </div>
      )}
      {b.scene === 'side' && SCENES[b.key] && (
        <div className="cine-side" key={`side-${beat}`}>
          {SCENES[b.key]}
        </div>
      )}

      {/* lower third */}
      <div className={`cine-lower ${b.phone ? 'phone-beat' : ''}`} key={`cap-${beat}`}>
        <span className="cine-kicker">
          <em>{b.hour}</em>
          <i />
          {b.place}
        </span>
        <b>{b.title}</b>
        <p>{b.text}</p>
        {clickable && (
          <span className="cine-hint">
            <i>▸</i> CLICK TO CONTINUE
          </span>
        )}
      </div>

      {b.phone && <PhonePanel onSos={onSos} />}
    </div>
  )
}

function PhonePanel({ onSos }) {
  const [sent, setSent] = useState(false)
  const press = () => {
    if (sent) return
    setSent(true)
    setTimeout(onSos, 1300) // let "SOS SENT" land before the mesh takes over
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
      {sent && <div className="phone-flash" />}
    </div>
  )
}
