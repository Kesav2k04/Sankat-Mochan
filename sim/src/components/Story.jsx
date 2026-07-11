import { useEffect, useState } from 'react'
import Lottie from './Lottie.jsx'
import aiRobot from '../assets/ai-robot.json'

/**
 * The opening act — the night of the disaster in five hand-animated scenes,
 * ending with the offline AI that will be listening. The final button drops
 * onto the live map, where the mesh wakes up and the victim presses SOS.
 */

const Hills = () => (
  <>
    <path d="M0 130 Q 60 84 130 118 T 250 108 T 360 122 V200 H0 Z" fill="#15222c" />
    <path d="M0 152 Q 80 116 170 142 T 360 148 V200 H0 Z" fill="#0e1820" />
  </>
)

function RainScene() {
  return (
    <svg viewBox="0 0 360 200" className="scene-svg">
      <rect width="360" height="200" fill="#0a141c" />
      <circle cx="300" cy="38" r="14" fill="#dfe8ee" opacity="0.85" />
      <circle cx="294" cy="34" r="13" fill="#0a141c" />
      <Hills />
      <g fill="#1b2a36">
        <ellipse cx="80" cy="34" rx="46" ry="15" />
        <ellipse cx="130" cy="42" rx="56" ry="17" />
        <ellipse cx="220" cy="30" rx="50" ry="15" />
      </g>
      {Array.from({ length: 20 }, (_, i) => (
        <line
          key={i}
          x1={14 + i * 18}
          y1="0"
          x2={8 + i * 18}
          y2="14"
          stroke="#4a7a99"
          strokeWidth="1.4"
          className="st-rain"
          style={{ animationDelay: `${(i % 7) * 0.13}s` }}
        />
      ))}
      <rect width="360" height="200" fill="#cfe6f5" className="st-flash" />
      <g fill="#233543">
        <rect x="60" y="138" width="18" height="13" />
        <path d="M58 138 L69 129 L80 138 Z" />
        <rect x="96" y="146" width="16" height="11" />
        <path d="M94 146 L104 138 L114 146 Z" />
      </g>
      <rect x="64" y="142" width="4" height="4" fill="#e8c46b" />
      <rect x="100" y="149" width="3" height="3" fill="#e8c46b" />
    </svg>
  )
}

function LandslideScene() {
  return (
    <svg viewBox="0 0 360 200" className="scene-svg st-shake">
      <rect width="360" height="200" fill="#0a141c" />
      <Hills />
      {/* the mass letting go */}
      <g className="st-slide">
        <path d="M96 52 Q 150 40 196 66 L 208 96 Q 160 112 118 100 L 96 78 Z" fill="#4a2e22" stroke="#5d3a29" />
        <circle cx="130" cy="98" r="5" fill="#5d3a29" />
        <circle cx="168" cy="106" r="4" fill="#3d2419" />
        <circle cx="196" cy="98" r="3.5" fill="#5d3a29" />
      </g>
      <path d="M 92 60 L 226 132" stroke="#3d2419" strokeWidth="26" strokeLinecap="round" opacity="0.55" />
      {/* village in the path */}
      <g fill="#233543">
        <rect x="228" y="140" width="18" height="13" />
        <path d="M226 140 L237 131 L248 140 Z" />
        <g className="st-tilt">
          <rect x="258" y="142" width="16" height="12" />
          <path d="M256 142 L266 134 L276 142 Z" />
        </g>
      </g>
      {Array.from({ length: 10 }, (_, i) => (
        <line key={i} x1={30 + i * 36} y1="0" x2={25 + i * 36} y2="12" stroke="#4a7a99" strokeWidth="1.2" className="st-rain" style={{ animationDelay: `${(i % 5) * 0.15}s` }} />
      ))}
    </svg>
  )
}

function PowerCutScene() {
  return (
    <svg viewBox="0 0 360 200" className="scene-svg">
      <rect width="360" height="200" fill="#0a141c" />
      <circle cx="304" cy="36" r="12" fill="#dfe8ee" opacity="0.8" />
      <circle cx="299" cy="33" r="11" fill="#0a141c" />
      <Hills />
      {/* pylon with a snapped line */}
      <g stroke="#3a4e5e" strokeWidth="2" fill="none">
        <path d="M60 150 L70 96 L80 150 M64 128 h32 M66 112 h24" />
        <path d="M92 112 Q 130 124 168 116" />
        <path d="M96 128 Q 118 140 128 146" className="st-snapped" />
      </g>
      <g className="st-spark">
        <path d="M128 144 l5 -3 l-2 6 l6 -2" stroke="#ffd36b" strokeWidth="1.6" fill="none" />
      </g>
      {/* the village going dark, window by window */}
      <g fill="#233543">
        {[176, 214, 252, 290].map((x) => (
          <g key={x}>
            <rect x={x} y="132" width="26" height="20" />
            <path d={`M${x - 3} 132 L${x + 13} 120 L${x + 29} 132 Z`} />
          </g>
        ))}
      </g>
      {[182, 220, 258, 296].map((x, i) => (
        <rect key={x} x={x} y="138" width="6" height="7" fill="#e8c46b" className="st-winoff" style={{ animationDelay: `${0.7 + i * 0.55}s` }} />
      ))}
      {[192, 230, 268, 306].map((x, i) => (
        <rect key={x} x={x} y="138" width="6" height="7" fill="#e8c46b" className="st-winoff" style={{ animationDelay: `${1.0 + i * 0.55}s` }} />
      ))}
    </svg>
  )
}

function TowerScene() {
  return (
    <svg viewBox="0 0 360 200" className="scene-svg">
      <rect width="360" height="200" fill="#0a141c" />
      <Hills />
      {/* lattice mast */}
      <g stroke="#3a4e5e" strokeWidth="2" fill="none">
        <path d="M168 156 L180 44 L192 156" />
        <path d="M171 128 h18 M173 104 h14 M175 82 h10 M177 62 h6" />
        <path d="M171 128 L189 104 M189 128 L173 104 M173 104 L187 82 M187 104 L175 82" strokeWidth="1.2" />
        <line x1="180" y1="44" x2="180" y2="30" />
      </g>
      {/* signal arcs dying */}
      {[0, 1, 2].map((i) => (
        <path
          key={i}
          d={`M ${186 + i * 9} ${26 - i * 5} a ${10 + i * 9} ${10 + i * 9} 0 0 1 0 ${18 + i * 14}`}
          transform="rotate(-90 190 32)"
          stroke="#5fb3d9"
          strokeWidth="2"
          fill="none"
          className="st-sig"
          style={{ animationDelay: `${0.8 + i * 0.5}s` }}
        />
      ))}
      {/* the crack and the verdict */}
      <polyline points="176,96 183,102 177,109 184,116" stroke="#d92d20" strokeWidth="1.8" fill="none" className="st-crack" />
      <g className="st-nosig">
        <line x1="216" y1="52" x2="240" y2="76" stroke="#d92d20" strokeWidth="3.4" strokeLinecap="round" />
        <line x1="240" y1="52" x2="216" y2="76" stroke="#d92d20" strokeWidth="3.4" strokeLinecap="round" />
        <text x="228" y="96" textAnchor="middle" fontSize="10" fill="#d92d20" fontFamily="monospace" letterSpacing="2">NO SIGNAL</text>
      </g>
    </svg>
  )
}

function LoraScene() {
  return (
    <svg viewBox="0 0 360 200" className="scene-svg">
      <rect width="360" height="200" fill="#0a141c" />
      <Hills />
      {[
        { x: 70, y: 120, d: 0 },
        { x: 180, y: 104, d: 0.6 },
        { x: 290, y: 126, d: 1.2 },
      ].map((n, i) => (
        <g key={i} transform={`translate(${n.x},${n.y})`}>
          <line x1="0" y1="8" x2="0" y2="30" stroke="#3a4e5e" strokeWidth="2.4" />
          <path d="M -10 8 L 0 -10 L 10 8 Z" fill="#2a1f08" stroke="#e6a23c" strokeWidth="1.8" />
          <circle r="2.2" cy="-10" fill="#e6a23c" />
          {[0, 1].map((k) => (
            <circle key={k} r="8" fill="none" stroke="#37c978" strokeWidth="1.4">
              <animate attributeName="r" values="8;44" dur="2s" begin={`${n.d + k}s`} repeatCount="indefinite" />
              <animate attributeName="opacity" values="0.9;0" dur="2s" begin={`${n.d + k}s`} repeatCount="indefinite" />
            </circle>
          ))}
        </g>
      ))}
      <line x1="80" y1="114" x2="170" y2="100" stroke="#37c978" strokeWidth="1.4" strokeDasharray="5 5" className="st-link" style={{ animationDelay: '1.4s' }} />
      <line x1="190" y1="100" x2="280" y2="120" stroke="#37c978" strokeWidth="1.4" strokeDasharray="5 5" className="st-link" style={{ animationDelay: '1.9s' }} />
      {/* solar + battery — why they survived the blackout */}
      <g transform="translate(318,40)">
        <circle r="9" fill="none" stroke="#e6a23c" strokeWidth="1.6" />
        {Array.from({ length: 8 }, (_, i) => {
          const a = (i * 45 * Math.PI) / 180
          return <line key={i} x1={Math.cos(a) * 12} y1={Math.sin(a) * 12} x2={Math.cos(a) * 16} y2={Math.sin(a) * 16} stroke="#e6a23c" strokeWidth="1.6" />
        })}
      </g>
      <g transform="translate(24,34)" stroke="#37c978" strokeWidth="1.6" fill="none">
        <rect x="0" y="0" width="26" height="13" rx="2.5" />
        <rect x="27" y="4" width="3.5" height="5" fill="#37c978" stroke="none" />
        <rect x="3" y="3" width="16" height="7" fill="#37c978" stroke="none" opacity="0.9" />
      </g>
    </svg>
  )
}

const CHAPTERS = [
  {
    hour: '02:00 · WAYANAD, KERALA',
    title: 'The rain will not stop',
    text: 'Forty-eight hours of monsoon rain has soaked the hills above the villages.',
    scene: <RainScene />,
    dur: 5,
  },
  {
    hour: 'HOUR 1 · 03:10',
    title: 'The hillside gives way',
    text: 'A landslide tears through the valley. Roads vanish. Houses are buried where they stood.',
    scene: <LandslideScene />,
    dur: 5.5,
  },
  {
    hour: 'HOUR 2 · 03:25',
    title: 'The power goes out',
    text: 'Transmission lines snap under the mud. Every village for ten kilometres goes dark.',
    scene: <PowerCutScene />,
    dur: 5.5,
  },
  {
    hour: '03:40',
    title: 'Towers down. No signal.',
    text: 'The cell tower is damaged and its backup drains. No calls, no internet — no way to ask for help.',
    scene: <TowerScene />,
    dur: 5.5,
  },
  {
    hour: '03:41',
    title: 'The mesh wakes up',
    text: 'Solar-charged LoRa modules across the zone switch to battery and find each other. They need no tower.',
    scene: <LoraScene />,
    dur: 5.5,
  },
  {
    hour: '04:05 · SAFE CAMP, OUTSIDE THE ZONE',
    title: 'Help is listening',
    text: 'An offline AI is waiting at the safe camp — it will transcribe, triage, suggest supplies, and task the nearest ranger. Now watch it happen on the ground.',
    scene: <Lottie data={aiRobot} className="scene-lottie big" />,
    dur: null, // final chapter waits for the button
  },
]

export default function Story({ onDone, onSkip }) {
  const [i, setI] = useState(0)
  const ch = CHAPTERS[i]
  const last = i === CHAPTERS.length - 1

  useEffect(() => {
    if (!ch.dur) return
    const t = setTimeout(() => setI((x) => Math.min(x + 1, CHAPTERS.length - 1)), ch.dur * 1000)
    return () => clearTimeout(t)
  }, [i, ch.dur])

  return (
    <div className="story" onClick={() => !last && setI((x) => x + 1)}>
      <button className="story-skip" onClick={(e) => { e.stopPropagation(); onSkip() }}>
        Skip story →
      </button>

      <div className="story-frame" key={i}>
        <div className="story-hour">{ch.hour}</div>
        <div className="story-scene">{ch.scene}</div>
        <h2 className="story-title">{ch.title}</h2>
        <p className="story-text">{ch.text}</p>
        {last && (
          <button className="story-cta" onClick={(e) => { e.stopPropagation(); onDone() }}>
            To the danger zone →
          </button>
        )}
      </div>

      <div className="story-dots">
        {CHAPTERS.map((c, k) => (
          <button key={k} className={k === i ? 'on' : k < i ? 'done' : ''} onClick={(e) => { e.stopPropagation(); setI(k) }}>
            {k === i && c.dur && <i style={{ animationDuration: `${c.dur}s` }} />}
          </button>
        ))}
      </div>
      {!last && <div className="story-hint">click to continue</div>}
    </div>
  )
}
