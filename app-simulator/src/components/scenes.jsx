/**
 * The story scenes — widescreen night vignettes that carry the film while the
 * map drifts underneath. Pure SVG + CSS, no assets, fully offline.
 *
 * One shared palette, four parallax depths, and every disaster plays ONCE and
 * holds its aftermath (fill-mode: forwards) — a landslide is not a loop.
 * Each scene scopes its keyframes with a prefix (rn-, sl-, pc-, tw-, ms-).
 */

const W = 840
const H = 360

const P = {
  skyTop: '#03060c',
  skyLow: '#102134',
  hillFar: '#101d2c',
  hillMid: '#16293c',
  hillNear: '#11212f',
  ground: '#0a141d',
  rim: '#3d5c78',
  fog: '#7fa3c0',
  moon: '#d7e7f5',
  warm: '#ffc76b',
  rain: '#8fb8d8',
  mud: '#4a2f1d',
  mudDark: '#33200f',
  mudLite: '#5f3e26',
  red: '#ff5147',
  amber: '#ffb347',
  green: '#3ddc84',
  teal: '#59c2e8',
}

/** Shared scenery ------------------------------------------------------- */

function Sky({ id }) {
  return (
    <>
      <defs>
        <linearGradient id={`${id}-sky`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={P.skyTop} />
          <stop offset="1" stopColor={P.skyLow} />
        </linearGradient>
        <radialGradient id={`${id}-vig`} cx="0.5" cy="0.42" r="0.75">
          <stop offset="0.55" stopColor="#000" stopOpacity="0" />
          <stop offset="1" stopColor="#000" stopOpacity="0.55" />
        </radialGradient>
        <filter id={`${id}-blur6`} x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="6" />
        </filter>
        <filter id={`${id}-blur14`} x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="14" />
        </filter>
      </defs>
      <rect width={W} height={H} fill={`url(#${id}-sky)`} />
    </>
  )
}

function Moon({ id, x = 690, y = 62, r = 18, veiled = true }) {
  return (
    <g>
      <defs>
        <mask id={`${id}-mooncut`}>
          <rect x={x - r - 2} y={y - r - 2} width={2 * r + 4} height={2 * r + 4} fill="#fff" />
          <circle cx={x - r * 0.48} cy={y - r * 0.22} r={r * 0.92} fill="#000" />
        </mask>
      </defs>
      <circle cx={x} cy={y} r={r * 2.8} fill={P.moon} opacity="0.08" filter={`url(#${id}-blur14)`} />
      <circle cx={x} cy={y} r={r} fill={P.moon} opacity="0.9" mask={`url(#${id}-mooncut)`} />
      {veiled && (
        <g filter={`url(#${id}-blur6)`} opacity="0.75">
          <ellipse cx={x - 12} cy={y + 7} rx={r * 2.3} ry={r * 0.65} fill="#0a141f" />
        </g>
      )}
    </g>
  )
}

/** Four hill planes, moonlit ridgelines, fog banks breathing between them. */
function Hills({ id }) {
  return (
    <g>
      <path d={`M0 176 Q 120 128 250 158 T 520 150 T 840 168 V${H} H0 Z`} fill={P.hillFar} />
      <path d="M0 176 Q 120 128 250 158 T 520 150 T 840 168" fill="none" stroke={P.rim} strokeWidth="1.2" opacity="0.4" />
      <rect x="0" y="168" width={W} height="26" fill={P.fog} opacity="0.07" filter={`url(#${id}-blur14)`} />
      <path d={`M0 216 Q 160 158 330 196 T 660 200 T 840 208 V${H} H0 Z`} fill={P.hillMid} />
      <path d="M0 216 Q 160 158 330 196 T 660 200 T 840 208" fill="none" stroke={P.rim} strokeWidth="1.1" opacity="0.32" />
      <rect x="0" y="206" width={W} height="30" fill={P.fog} opacity="0.08" filter={`url(#${id}-blur14)`} />
      <path d={`M0 276 Q 200 226 420 262 T 840 272 V${H} H0 Z`} fill={P.hillNear} />
      <path d="M0 276 Q 200 226 420 262 T 840 272" fill="none" stroke={P.rim} strokeWidth="1" opacity="0.22" />
      <path d={`M0 322 Q 260 296 520 314 T 840 318 V${H} H0 Z`} fill={P.ground} />
    </g>
  )
}

function House({ x, y, s = 1, lit = true, litClass = '' }) {
  return (
    <g transform={`translate(${x},${y}) scale(${s})`}>
      <rect x="-12" y="-10" width="24" height="13" fill="#152331" />
      <path d="M -14 -10 L 0 -21 L 14 -10 Z" fill="#1c2e3f" />
      {lit && (
        <g className={litClass}>
          <rect x="-5" y="-7" width="8" height="8" fill={P.warm} />
          <rect x="-8" y="-10" width="14" height="14" fill={P.warm} opacity="0.14" rx="4" />
        </g>
      )}
    </g>
  )
}

function Pine({ x, y, s = 1, className = '' }) {
  return (
    <g transform={`translate(${x},${y}) scale(${s})`} className={className}>
      <line x1="0" y1="0" x2="0" y2="-6" stroke="#0a1420" strokeWidth="2.4" />
      <path d="M -7 -4 L 0 -18 L 7 -4 Z" fill="#0e1d2a" />
      <path d="M -5.4 -12 L 0 -24 L 5.4 -12 Z" fill="#102030" />
    </g>
  )
}

/** Rain layers: three depths, different speed/weight, all translating down-screen. */
function Rain({ layer = 'near', count = 16, className }) {
  const conf = {
    far: { len: 10, w: 0.8, op: 0.3 },
    mid: { len: 16, w: 1.1, op: 0.42 },
    near: { len: 26, w: 1.7, op: 0.55 },
  }[layer]
  return (
    <g className={className} opacity={conf.op} stroke={P.rain} strokeWidth={conf.w} strokeLinecap="round">
      {Array.from({ length: count }, (_, i) => {
        const x = (i * 997) % W // pseudo-scatter, deterministic
        const y = (i * 431) % H
        return <line key={i} x1={x} y1={y} x2={x - conf.len * 0.28} y2={y + conf.len} style={{ animationDelay: `${-(i % 10) * 0.17}s` }} className="rr" />
      })}
    </g>
  )
}

function Vignette({ id }) {
  return <rect width={W} height={H} fill={`url(#${id}-vig)`} pointerEvents="none" />
}

/** 02:00 — the rain will not stop -------------------------------------- */

function RainScene() {
  const id = 'rn'
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="scene-svg" preserveAspectRatio="xMidYMid slice">
      <style>{`
        .rn-kb { animation: rn-kb 9s ease-out forwards; transform-origin: 50% 55%; }
        @keyframes rn-kb { from { transform: scale(1); } to { transform: scale(1.055); } }
        .rn-cloud1 { animation: rn-drift 26s linear infinite alternate; }
        .rn-cloud2 { animation: rn-drift 34s linear infinite alternate-reverse; }
        @keyframes rn-drift { from { transform: translateX(-14px); } to { transform: translateX(18px); } }
        .rn-rain-far .rr { animation: rn-fall-far 1.5s linear infinite; }
        .rn-rain-mid .rr { animation: rn-fall-mid 1.05s linear infinite; }
        .rn-rain-near .rr { animation: rn-fall-near 0.62s linear infinite; }
        @keyframes rn-fall-far { from { transform: translateY(-70px); } to { transform: translateY(390px); } }
        @keyframes rn-fall-mid { from { transform: translateY(-80px); } to { transform: translateY(400px); } }
        @keyframes rn-fall-near { from { transform: translateY(-90px); } to { transform: translateY(410px); } }
        .rn-flash { opacity: 0; animation: rn-flash 7s ease-out infinite; mix-blend-mode: screen; }
        @keyframes rn-flash { 0%, 55.5%, 58.6%, 100% { opacity: 0; } 56% { opacity: 0.85; } 56.8% { opacity: 0.12; } 57.6% { opacity: 0.55; } }
        .rn-ridgeflash { opacity: 0; animation: rn-ridgeflash 7s ease-out infinite; }
        @keyframes rn-ridgeflash { 0%, 55.5%, 58.6%, 100% { opacity: 0; } 56% { opacity: 0.7; } 56.8% { opacity: 0.1; } 57.6% { opacity: 0.45; } }
        .rn-bolt { opacity: 0; animation: rn-bolt 7s linear infinite; }
        @keyframes rn-bolt { 0%, 55.5%, 58.2%, 100% { opacity: 0; } 56%, 57.8% { opacity: 0.95; } }
        .rn-win { animation: rn-win 4.2s steps(2, end) infinite; }
        @keyframes rn-win { 0%, 92%, 100% { opacity: 1; } 94%, 96% { opacity: 0.4; } }
        .rn-river { animation: rn-river 2.6s linear infinite; }
        @keyframes rn-river { to { stroke-dashoffset: -46; } }
        .rn-splash { animation: rn-splash 0.9s ease-out infinite; transform-box: fill-box; transform-origin: center; }
        @keyframes rn-splash { 0% { transform: scale(0.2); opacity: 0.7; } 80%, 100% { transform: scale(1.4); opacity: 0; } }
      `}</style>
      <Sky id={id} />
      <g className="rn-kb">
        <Moon id={id} />
        <g fill="#0a141f">
          <g className="rn-cloud1">
            <ellipse cx="180" cy="52" rx="130" ry="26" filter={`url(#${id}-blur6)`} />
            <ellipse cx="320" cy="76" rx="150" ry="24" filter={`url(#${id}-blur6)`} opacity="0.85" />
          </g>
          <g className="rn-cloud2">
            <ellipse cx="600" cy="44" rx="160" ry="24" filter={`url(#${id}-blur6)`} opacity="0.9" />
            <ellipse cx="740" cy="86" rx="120" ry="20" filter={`url(#${id}-blur6)`} opacity="0.7" />
          </g>
        </g>
        <Hills id={id} />
        {/* the ridge answers the lightning */}
        <path className="rn-ridgeflash" d="M0 176 Q 120 128 250 158 T 520 150 T 840 168" fill="none" stroke="#7fa8cd" strokeWidth="1.6" />

        {/* the village holding on — a few warm windows in the dark */}
        <g>
          <House x={430} y={300} litClass="rn-win" />
          <House x={472} y={306} s={0.85} litClass="rn-win" />
          <House x={510} y={300} s={0.9} lit={false} />
          <Pine x={392} y={306} s={0.9} />
          <Pine x={545} y={308} />
          {/* street lamp with a cone of light through the rain */}
          <g transform="translate(560,268)">
            <line x1="0" y1="0" x2="0" y2="36" stroke="#16232f" strokeWidth="2.6" />
            <circle cy="-2" r="3" fill={P.warm} opacity="0.95" />
            <path d="M -2 0 L -16 40 L 16 40 L 2 0 Z" fill={P.warm} opacity="0.07" />
          </g>
        </g>

        {/* swollen river creeping up the valley floor */}
        <path d={`M0 336 Q 300 322 520 332 T 840 330 V${H} H0 Z`} fill="#0b2233" opacity="0.9" />
        <g stroke="#28506b" strokeWidth="1.4" opacity="0.6">
          <path className="rn-river" d="M20 340 H 820" strokeDasharray="16 30" />
          <path className="rn-river" d="M0 348 H 840" strokeDasharray="10 36" style={{ animationDelay: '-1.2s' }} />
        </g>
        {[120, 300, 620, 760].map((x, i) => (
          <ellipse key={x} className="rn-splash" cx={x} cy={341} rx="6" ry="2" fill="none" stroke={P.rain} strokeWidth="1" style={{ animationDelay: `${i * 0.23}s` }} />
        ))}

        <Rain layer="far" count={28} className="rn-rain-far" />
        <Rain layer="mid" count={24} className="rn-rain-mid" />
        <Rain layer="near" count={18} className="rn-rain-near" />

        {/* lightning: the sky itself fires, and a bolt rakes the far ridge */}
        <rect width={W} height={H} className="rn-flash" fill={`url(#${id}-lightning)`} />
        <defs>
          <radialGradient id={`${id}-lightning`} cx="0.32" cy="0.1" r="0.9">
            <stop offset="0" stopColor="#dff0ff" stopOpacity="0.9" />
            <stop offset="0.45" stopColor="#9cc4e8" stopOpacity="0.35" />
            <stop offset="1" stopColor="#000" stopOpacity="0" />
          </radialGradient>
        </defs>
        <polyline className="rn-bolt" points="268,0 258,42 276,58 252,96 270,112 250,150" fill="none" stroke="#eaf6ff" strokeWidth="2.2" strokeLinejoin="round" />
      </g>
      <Vignette id={id} />
    </svg>
  )
}

/** 03:10 — the hillside gives way --------------------------------------- */

function LandslideScene() {
  const id = 'sl'
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="scene-svg" preserveAspectRatio="xMidYMid slice">
      <style>{`
        .sl-kb { animation: sl-kb 10s ease-out forwards; transform-origin: 42% 55%; }
        @keyframes sl-kb { from { transform: scale(1.02); } to { transform: scale(1.09); } }
        .sl-quake { animation: sl-quake 1.3s linear 0.9s 1; }
        @keyframes sl-quake {
          0%, 100% { transform: translate(0, 0); }
          12% { transform: translate(-3px, 2px); } 26% { transform: translate(3px, -2px); }
          42% { transform: translate(-2.4px, -1.6px); } 58% { transform: translate(2px, 1.8px); }
          74% { transform: translate(-1.2px, 0.8px); } 88% { transform: translate(0.8px, -0.6px); }
        }
        .sl-crack { stroke-dasharray: 210; stroke-dashoffset: 210; animation: sl-crack 0.9s ease-out 1s forwards; }
        @keyframes sl-crack { to { stroke-dashoffset: 0; } }
        .sl-mass { animation: sl-mass 2.6s cubic-bezier(0.45, 0.02, 0.85, 0.4) 1.7s forwards; }
        @keyframes sl-mass { to { transform: translate(158px, 148px) rotate(4deg); } }
        .sl-flow { stroke-dasharray: 400; stroke-dashoffset: 400; animation: sl-flow 2.3s cubic-bezier(0.5, 0.05, 0.9, 0.4) 1.8s forwards; }
        @keyframes sl-flow { to { stroke-dashoffset: 0; } }
        .sl-boulder { animation: sl-roll 2.6s linear 1.7s forwards; transform-box: fill-box; transform-origin: center; }
        @keyframes sl-roll { to { transform: rotate(520deg); } }
        .sl-pine-a { animation: sl-tip 1.1s ease-in 2s forwards; transform-box: fill-box; transform-origin: center bottom; }
        .sl-pine-b { animation: sl-tip 1s ease-in 2.5s forwards; transform-box: fill-box; transform-origin: center bottom; }
        @keyframes sl-tip { to { transform: rotate(-74deg); opacity: 0.85; } }
        .sl-dust { opacity: 0; animation: sl-dust 2.4s ease-out 3.5s forwards; transform-box: fill-box; transform-origin: center bottom; }
        @keyframes sl-dust { 0% { opacity: 0; transform: scale(0.25); } 22% { opacity: 0.5; } 100% { opacity: 0; transform: scale(1.9) translateY(-14px); } }
        .sl-impact { animation: sl-quake 0.9s linear 3.9s 1; }
        .sl-bury { opacity: 0; animation: sl-bury 1s cubic-bezier(0.5, 0.05, 0.8, 0.4) 3.8s forwards; transform-box: fill-box; transform-origin: center bottom; }
        @keyframes sl-bury { 0% { opacity: 0; transform: translate(-30px, -26px) scale(0.5); } 30% { opacity: 1; } 100% { opacity: 1; transform: translate(0, 0) scale(1); } }
        .sl-tilt { animation: sl-tilt 1.2s ease-in 4.1s forwards; transform-box: fill-box; transform-origin: right bottom; }
        @keyframes sl-tilt { to { transform: rotate(-13deg); } }
        .sl-winout { animation: sl-winout 0.4s steps(3, end) 4.6s forwards; }
        @keyframes sl-winout { to { opacity: 0; } }
        .sl-rain .rr { animation: sl-fall 0.95s linear infinite; }
        @keyframes sl-fall { from { transform: translateY(-80px); } to { transform: translateY(400px); } }
      `}</style>
      <Sky id={id} />
      <g className="sl-kb">
        <g className="sl-quake">
          <g className="sl-impact">
            <Moon id={id} x={730} y={52} r={15} />
            <Hills id={id} />

            {/* the flank that fails: a broad terraced slope over the valley */}
            <g>
              <path d={`M -20 150 L 150 108 Q 250 112 330 168 L 386 234 Q 300 262 180 252 L -20 224 Z`} fill="#182c40" />
              <path d="M -20 150 L 150 108 Q 250 112 330 168" fill="none" stroke={P.rim} strokeWidth="1.2" opacity="0.5" />
              {/* tea terraces stepping down the flank */}
              <g stroke="#24405c" strokeWidth="1.7" fill="none" opacity="0.85">
                <path d="M 40 152 Q 170 122 300 168" />
                <path d="M 26 172 Q 178 138 322 186" />
                <path d="M 14 192 Q 186 154 344 206" />
                <path d="M 2 212 Q 194 172 362 226" />
                <path d="M -10 232 Q 200 192 376 244" />
              </g>
              {/* trees holding the ridge */}
              <Pine x={64} y={148} s={0.7} />
              <Pine x={294} y={172} s={0.65} />
            </g>

            {/* the crack that opens along the upper terraces */}
            <path className="sl-crack" d="M 96 148 L 142 152 L 134 164 L 188 166 L 180 180 L 236 184" fill="none" stroke="#0a0f16" strokeWidth="3.4" strokeLinejoin="round" />

            {/* the flow track the mass gouges out of the flank */}
            <path className="sl-flow" d="M 158 160 Q 226 208 282 262 T 400 330" fill="none" stroke={P.mudDark} strokeWidth="42" strokeLinecap="round" opacity="0.9" />
            <path className="sl-flow" d="M 164 156 Q 234 206 292 260 T 408 326" fill="none" stroke={P.mud} strokeWidth="22" strokeLinecap="round" style={{ animationDelay: '2s' }} />

            {/* the mass itself: a jagged tongue of hillside, boulders, trees going with it */}
            <g className="sl-mass">
              <path
                d="M 108 132 L 146 118 L 190 124 L 222 140 L 238 162 L 224 182 L 186 196 L 144 194 L 114 176 L 100 152 Z"
                fill={P.mud}
                stroke={P.mudLite}
                strokeWidth="2"
                strokeLinejoin="round"
              />
              <path d="M 126 150 Q 168 132 210 150 M 118 166 Q 166 150 218 168" fill="none" stroke={P.mudLite} strokeWidth="2" opacity="0.65" />
              <circle className="sl-boulder" cx="140" cy="182" r="8" fill={P.mudDark} stroke={P.mudLite} strokeWidth="1.2" />
              <circle className="sl-boulder" cx="196" cy="190" r="6" fill={P.mudLite} style={{ animationDelay: '1.9s' }} />
              <circle className="sl-boulder" cx="226" cy="172" r="5" fill={P.mudDark} stroke={P.mudLite} strokeWidth="1" style={{ animationDelay: '2.1s' }} />
              <Pine x={140} y={166} s={0.85} className="sl-pine-a" />
              <Pine x={206} y={176} s={0.75} className="sl-pine-b" />
            </g>

            {/* dust blooming where it lands */}
            <g fill="#8fa3b8">
              <ellipse className="sl-dust" cx="368" cy="314" rx="58" ry="22" filter={`url(#${id}-blur14)`} />
              <ellipse className="sl-dust" cx="428" cy="324" rx="44" ry="18" filter={`url(#${id}-blur14)`} style={{ animationDelay: '3.7s' }} />
              <ellipse className="sl-dust" cx="316" cy="326" rx="38" ry="15" filter={`url(#${id}-blur14)`} style={{ animationDelay: '3.9s' }} />
            </g>

            {/* the two houses in the path */}
            <g>
              <House x={396} y={326} s={1.1} lit={false} />
              <path className="sl-bury" d="M 364 330 Q 386 300 412 314 Q 432 322 428 332 L 364 332 Z" fill={P.mud} stroke={P.mudLite} strokeWidth="1.6" />
              <g className="sl-tilt">
                <House x={468} y={328} s={1.05} litClass="sl-winout" />
              </g>
              <House x={540} y={324} s={0.9} />
              <Pine x={588} y={330} s={0.9} />
            </g>

            <Rain layer="mid" count={16} className="sl-rain" />
            <Rain layer="near" count={12} className="sl-rain" />
          </g>
        </g>
      </g>
      <Vignette id={id} />
    </svg>
  )
}

/** 03:25 — the power goes out ------------------------------------------- */

function PowerCutScene() {
  const id = 'pc'
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="scene-svg" preserveAspectRatio="xMidYMid slice">
      <style>{`
        .pc-kb { animation: pc-kb 9s ease-out forwards; transform-origin: 50% 40%; }
        @keyframes pc-kb { from { transform: scale(1.01); } to { transform: scale(1.06); } }
        .pc-mud { opacity: 0; animation: pc-mud 0.8s ease-in 0.5s forwards; }
        @keyframes pc-mud { 0% { opacity: 0; transform: translate(-46px, -30px); } 40% { opacity: 1; } 100% { opacity: 1; transform: translate(0, 0); } }
        .pc-lean { animation: pc-lean 1.6s cubic-bezier(0.6, 0.04, 0.9, 0.4) 1.2s forwards; transform-box: fill-box; transform-origin: 30% 100%; }
        @keyframes pc-lean { to { transform: rotate(11deg); } }
        .pc-cable-ok { animation: pc-fadeout 0.1s linear 2.6s forwards; }
        @keyframes pc-fadeout { to { opacity: 0; } }
        .pc-cable-snapped { opacity: 0; animation: pc-snapin 0.1s linear 2.6s forwards; }
        @keyframes pc-snapin { to { opacity: 1; } }
        .pc-cable-fall { animation: pc-fall 1s cubic-bezier(0.5, 0, 0.9, 0.5) 2.6s forwards; transform-box: fill-box; transform-origin: left top; }
        @keyframes pc-fall { to { transform: rotate(38deg); } }
        .pc-spark { opacity: 0; animation: pc-spark 1.6s steps(2, start) 2.6s 2; }
        @keyframes pc-spark { 0%, 12% { opacity: 1; } 18%, 44% { opacity: 0; } 50%, 60% { opacity: 0.9; } 66%, 100% { opacity: 0; } }
        .pc-w1 { animation: pc-out 0.35s steps(2, end) 3.4s forwards; }
        .pc-w2 { animation: pc-out 0.35s steps(2, end) 4.05s forwards; }
        .pc-w3 { animation: pc-out 0.35s steps(2, end) 4.7s forwards; }
        .pc-w4 { animation: pc-out 0.35s steps(2, end) 5.3s forwards; }
        @keyframes pc-out { to { opacity: 0; } }
        .pc-lamp { animation: pc-lampflicker 0.7s steps(2, end) 5.6s forwards; }
        @keyframes pc-lampflicker { 0% { opacity: 1; } 35% { opacity: 0.2; } 55% { opacity: 0.9; } 100% { opacity: 0; } }
        .pc-batt { animation: pc-batt 2.4s steps(2, end) 5.8s forwards; }
        @keyframes pc-batt { 0%, 55% { opacity: 1; } 62%, 74% { opacity: 0.25; } 80% { opacity: 0.9; } 100% { opacity: 0; } }
        .pc-gloom { opacity: 0; animation: pc-gloom 2.4s ease-in 5.4s forwards; }
        @keyframes pc-gloom { to { opacity: 0.5; } }
        .pc-rain .rr { animation: pc-fall-r 1.15s linear infinite; }
        @keyframes pc-fall-r { from { transform: translateY(-80px); } to { transform: translateY(400px); } }
      `}</style>
      <Sky id={id} />
      <g className="pc-kb">
        <Hills id={id} />

        {/* transmission line marching along the mid ridge */}
        <g stroke="#24394d" strokeWidth="2.2" fill="none">
          <g>
            <path d="M120 208 L134 128 L148 208 M124 176 h44 M128 152 h36" />
            <path d="M120 208 L148 208" />
          </g>
          <g className="pc-lean">
            <path d="M400 196 L414 112 L428 196 M404 162 h44 M408 136 h36" />
          </g>
          <g>
            <path d="M690 204 L704 124 L718 204 M694 172 h44 M698 148 h36" />
          </g>
          {/* healthy cables */}
          <g className="pc-cable-ok" strokeWidth="1.7" opacity="0.8">
            <path d="M148 150 Q 275 186 404 134" />
            <path d="M428 134 Q 560 188 694 146" />
          </g>
          {/* snapped: left half whips down, right half sags */}
          <g className="pc-cable-snapped" strokeWidth="1.7" opacity="0.8">
            <path className="pc-cable-fall" d="M148 150 Q 230 178 288 172" />
            <path d="M428 140 Q 560 196 694 146" />
          </g>
        </g>

        {/* the mudflow that took the pylon's footing */}
        <path className="pc-mud" d="M 356 200 Q 396 184 436 198 L 446 210 Q 400 222 362 212 Z" fill={P.mud} opacity="0.9" />

        {/* sparks at the break */}
        <g className="pc-spark" stroke={P.warm} strokeWidth="2" strokeLinecap="round">
          <path d="M288 170 l10 -7 M290 174 l12 2 M286 176 l7 10 M284 168 l-4 -10" />
          <circle cx="288" cy="171" r="2.6" fill="#fff2d0" stroke="none" />
        </g>

        {/* the village grid below — then, cluster by cluster, the dark */}
        <g>
          {[
            { x: 150, y: 316, w: 'pc-w1' }, { x: 196, y: 322, w: 'pc-w1' }, { x: 238, y: 318, w: 'pc-w2' },
            { x: 320, y: 324, w: 'pc-w1' }, { x: 362, y: 318, w: 'pc-w3' }, { x: 404, y: 326, w: 'pc-w2' },
            { x: 486, y: 320, w: 'pc-w2' }, { x: 530, y: 326, w: 'pc-w4' }, { x: 572, y: 320, w: 'pc-w3' },
            { x: 650, y: 324, w: 'pc-w3' }, { x: 694, y: 318, w: 'pc-w4' }, { x: 738, y: 324, w: 'pc-w1' },
          ].map((h, i) => (
            <House key={i} x={h.x} y={h.y} s={0.95} litClass={h.w} />
          ))}
          {/* street lamps die last, flickering */}
          {[275, 610].map((x) => (
            <g key={x} transform={`translate(${x},288)`}>
              <line x1="0" y1="0" x2="0" y2="34" stroke="#16232f" strokeWidth="2.4" />
              <g className="pc-lamp">
                <circle cy="-2" r="2.8" fill={P.warm} opacity="0.95" />
                <path d="M -2 0 L -14 36 L 14 36 L 2 0 Z" fill={P.warm} opacity="0.07" />
              </g>
            </g>
          ))}
          {/* one house on inverter power — it holds a little longer */}
          <g className="pc-batt">
            <rect x="441" y="316" width="6" height="6" fill="#bfe3ff" />
          </g>
          <House x={444} y={322} s={0.95} lit={false} />
        </g>

        <Rain layer="far" count={14} className="pc-rain" />
        <Rain layer="mid" count={10} className="pc-rain" />

        {/* the dark settling over everything — but the moon stays above it */}
        <rect className="pc-gloom" width={W} height={H} fill="#010409" />
        <Moon id={id} x={112} y={58} r={17} />
      </g>
      <Vignette id={id} />
    </svg>
  )
}

/** 03:40 — towers down, no signal --------------------------------------- */

function TowerScene() {
  const id = 'tw'
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="scene-svg" preserveAspectRatio="xMidYMid slice">
      <style>{`
        .tw-kb { animation: tw-kb 9s ease-out forwards; transform-origin: 58% 45%; }
        @keyframes tw-kb { from { transform: scale(1.03); } to { transform: scale(1.085); } }
        .tw-beacon { animation: tw-beacon 1.6s ease-in-out infinite; }
        @keyframes tw-beacon { 0%, 100% { opacity: 1; } 50% { opacity: 0.12; } }
        .tw-sig-ok { animation: tw-sig 1.3s ease-out infinite; animation-iteration-count: 3; opacity: 0; transform-box: fill-box; transform-origin: center; }
        @keyframes tw-sig { 0% { opacity: 0.8; transform: scale(0.4); } 100% { opacity: 0; transform: scale(1.5); } }
        .tw-sig-weak { animation: tw-sigweak 1.7s ease-out 4.2s 2; opacity: 0; transform-box: fill-box; transform-origin: center; }
        @keyframes tw-sigweak { 0% { opacity: 0.35; transform: scale(0.4); } 60% { opacity: 0.06; } 100% { opacity: 0; transform: scale(0.95); } }
        .tw-bar1 { animation: tw-barout 0.2s steps(2, end) 2.2s forwards; }
        .tw-bar2 { animation: tw-barout 0.2s steps(2, end) 3.2s forwards; }
        .tw-bar3 { animation: tw-barout 0.2s steps(2, end) 4.4s forwards; }
        .tw-bar4 { animation: tw-barout 0.2s steps(2, end) 5.4s forwards; }
        @keyframes tw-barout { to { opacity: 0.14; } }
        .tw-x { opacity: 0; animation: tw-xin 0.3s steps(2, start) 5.7s forwards; }
        @keyframes tw-xin { to { opacity: 1; } }
        .tw-hutlight { animation: tw-hut 1.4s steps(2, end) 4.6s forwards; }
        @keyframes tw-hut { 0%, 40% { opacity: 1; } 48%, 62% { opacity: 0.2; } 70% { opacity: 0.85; } 100% { opacity: 0; } }
        .tw-stamp { opacity: 0; animation: tw-stampin 0.25s steps(2, start) 6s forwards, tw-glitch 2.4s steps(2, end) 6.3s infinite; }
        @keyframes tw-stampin { to { opacity: 1; } }
        @keyframes tw-glitch { 0%, 91%, 100% { transform: translate(0, 0); } 93% { transform: translate(-2px, 1px); } 95% { transform: translate(1.6px, -1px); } }
        .tw-fog { animation: tw-fogdrift 14s linear infinite alternate; }
        @keyframes tw-fogdrift { from { transform: translateX(-30px); } to { transform: translateX(36px); } }
        .tw-rain .rr { animation: tw-fall 1.2s linear infinite; }
        @keyframes tw-fall { from { transform: translateY(-80px); } to { transform: translateY(400px); } }
      `}</style>
      <Sky id={id} />
      <g className="tw-kb">
        <Moon id={id} x={296} y={58} r={15} />
        <Hills id={id} />

        {/* the tower on its ridge — the tallest thing for ten kilometres */}
        <g transform="translate(500,262)">
          {/* lattice mast */}
          <g stroke="#2b3f52" strokeWidth="2.4" fill="none">
            <path d="M -26 0 L -8 -168 M 26 0 L 8 -168" />
            <path d="M -22 -28 h44 M -18 -62 h36 M -14 -96 h28 M -11 -128 h22 M -8 -152 h16" />
            <path d="M -22 -28 L 18 -62 M 22 -28 L -18 -62 M -18 -62 L 14 -96 M 18 -62 L -14 -96 M -14 -96 L 11 -128 M 14 -96 L -11 -128" strokeWidth="1.3" />
            <line x1="0" y1="-168" x2="0" y2="-190" />
          </g>
          {/* antenna panels + dish */}
          <g fill="#31485e">
            <rect x="-16" y="-166" width="6" height="22" rx="1.5" transform="rotate(-8 -13 -155)" />
            <rect x="10" y="-166" width="6" height="22" rx="1.5" transform="rotate(8 13 -155)" />
            <rect x="-3" y="-172" width="6" height="24" rx="1.5" />
            <ellipse cx="-14" cy="-118" rx="7" ry="9" transform="rotate(-24 -14 -118)" fill="#243748" />
          </g>
          {/* aviation beacon — the only light that survives the night */}
          <circle className="tw-beacon" cy="-192" r="3.4" fill={P.red} />
          <circle className="tw-beacon" cy="-192" r="8" fill={P.red} opacity="0.25" filter={`url(#${id}-blur6)`} />

          {/* signal rings: healthy, then weak, then nothing */}
          {[0, 0.42, 0.84].map((d) => (
            <circle key={d} className="tw-sig-ok" cy="-186" r="30" fill="none" stroke={P.teal} strokeWidth="2" style={{ animationDelay: `${d}s` }} />
          ))}
          {[0, 0.8].map((d) => (
            <circle key={d} className="tw-sig-weak" cy="-186" r="26" fill="none" stroke={P.teal} strokeWidth="1.6" style={{ animationDelay: `${4.2 + d}s` }} />
          ))}

          {/* equipment hut on backup power */}
          <g transform="translate(-58,-2)">
            <rect x="-14" y="-14" width="28" height="14" fill="#101c29" />
            <path d="M -16 -14 L 0 -24 L 16 -14 Z" fill="#15222f" />
            <rect className="tw-hutlight" x="-5" y="-10" width="7" height="7" fill={P.warm} />
          </g>
        </g>

        {/* fog band sliding across the ridge */}
        <rect className="tw-fog" x="-60" y="196" width="960" height="42" fill={P.fog} opacity="0.08" filter={`url(#${id}-blur14)`} />

        {/* phone status, top-left: the bars drain to an X */}
        <g transform="translate(64,44)" fontFamily="ui-monospace, monospace">
          <rect x="-18" y="-22" width="118" height="44" rx="8" fill="#060e16" opacity="0.72" stroke="#22374b" />
          {[0, 1, 2, 3].map((k) => (
            <rect key={k} className={`tw-bar${4 - k}`} x={k * 12} y={-2 - k * 5} width="8" height={6 + k * 5} fill={P.teal} />
          ))}
          <g className="tw-x" stroke={P.red} strokeWidth="2.6" strokeLinecap="round">
            <line x1="62" y1="-8" x2="78" y2="8" />
            <line x1="78" y1="-8" x2="62" y2="8" />
          </g>
        </g>

        {/* the verdict */}
        <g className="tw-stamp" transform="translate(660,150)">
          <rect x="-74" y="-17" width="148" height="34" fill="#0a0405" opacity="0.75" stroke={P.red} strokeWidth="1.4" />
          <text textAnchor="middle" y="6" fontFamily="ui-monospace, monospace" fontSize="16" letterSpacing="6" fill={P.red}>NO SIGNAL</text>
        </g>

        <Rain layer="far" count={12} className="tw-rain" />
      </g>
      <Vignette id={id} />
    </svg>
  )
}

/** 03:41 — the mesh wakes up -------------------------------------------- */

function LoraNode({ x, y, s = 1, wake = 0.8 }) {
  return (
    <g transform={`translate(${x},${y}) scale(${s})`}>
      {/* pole, guys, box, whip antenna, solar panel */}
      <line x1="0" y1="0" x2="0" y2="-56" stroke="#2b3f52" strokeWidth="3" />
      <path d="M 0 -40 L -18 0 M 0 -40 L 18 0" stroke="#22374b" strokeWidth="1" />
      <rect x="-8" y="-46" width="16" height="20" rx="2.5" fill="#101c29" stroke="#2b3f52" strokeWidth="1.4" />
      <line x1="0" y1="-46" x2="0" y2="-78" stroke="#3a5268" strokeWidth="1.8" />
      <circle cy="-78" r="1.8" fill="#3a5268" />
      <g transform="translate(13,-58) rotate(-28)">
        <rect x="-11" y="-7" width="22" height="14" rx="1.5" fill="#12253a" stroke="#2f4a63" strokeWidth="1.2" />
        <path d="M -11 -2.3 h22 M -11 2.3 h22 M -3.7 -7 v14 M 3.7 -7 v14" stroke="#2f4a63" strokeWidth="0.8" />
        <rect className="ms-glint" x="-11" y="-7" width="6" height="14" fill="#cfe6f5" opacity="0" />
      </g>
      {/* the LED and the wake ring */}
      <circle className="ms-led" cy="-36" r="2.6" fill={P.green} opacity="0.12" style={{ animationDelay: `${wake}s` }} />
      <circle className="ms-ring" cy="-36" r="10" fill="none" stroke={P.green} strokeWidth="1.6" opacity="0" style={{ animationDelay: `${wake}s` }} />
      <circle className="ms-ring" cy="-36" r="10" fill="none" stroke={P.green} strokeWidth="1.2" opacity="0" style={{ animationDelay: `${wake + 0.5}s` }} />
    </g>
  )
}

function MeshScene() {
  const id = 'ms'
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="scene-svg" preserveAspectRatio="xMidYMid slice">
      <style>{`
        .ms-kb { animation: ms-kb 10s ease-out forwards; transform-origin: 50% 52%; }
        @keyframes ms-kb { from { transform: scale(1.045); } to { transform: scale(1); } }
        .ms-star { animation: ms-star 3.4s ease-in-out infinite; }
        @keyframes ms-star { 0%, 100% { opacity: 0.15; } 50% { opacity: 0.85; } }
        .ms-clouds-l { animation: ms-part-l 9s ease-out forwards; }
        .ms-clouds-r { animation: ms-part-r 9s ease-out forwards; }
        @keyframes ms-part-l { to { transform: translateX(-90px); opacity: 0.5; } }
        @keyframes ms-part-r { to { transform: translateX(90px); opacity: 0.5; } }
        .ms-led { animation: ms-ledon 0.5s steps(2, start) forwards; }
        @keyframes ms-ledon { to { opacity: 1; } }
        .ms-ring { transform-box: fill-box; transform-origin: center; animation: ms-ringout 1.6s ease-out forwards; }
        @keyframes ms-ringout { 0% { opacity: 0.85; transform: scale(0.3); } 100% { opacity: 0; transform: scale(3.4); } }
        .ms-glint { animation: ms-glint 5s ease-in-out 2.4s infinite; }
        @keyframes ms-glint { 0%, 78%, 100% { opacity: 0; } 84% { opacity: 0.5; } 90% { opacity: 0; } }
        .ms-link { stroke-dasharray: 7 7; opacity: 0; }
        .ms-link-a { animation: ms-linkin 1s ease-out 2.2s forwards, ms-march 1.4s linear 3.2s infinite; }
        .ms-link-b { animation: ms-linkin 1s ease-out 3.4s forwards, ms-march 1.4s linear 4.4s infinite; }
        @keyframes ms-linkin { from { opacity: 0; } to { opacity: 0.8; } }
        @keyframes ms-march { to { stroke-dashoffset: -28; } }
        .ms-pkt { opacity: 0; animation: ms-pktin 0.3s linear 4.6s forwards; }
        @keyframes ms-pktin { to { opacity: 1; } }
      `}</style>
      <Sky id={id} />
      <g className="ms-kb">
        {/* rain has stopped: stars come out */}
        <g fill="#cfe2f3">
          {Array.from({ length: 34 }, (_, i) => {
            const x = (i * 761) % W
            const y = ((i * 389) % 130) + 8
            return <circle key={i} className="ms-star" cx={x} cy={y} r={(i % 3) * 0.35 + 0.5} style={{ animationDelay: `${(i % 9) * 0.45}s` }} />
          })}
        </g>
        <Moon id={id} x={676} y={58} r={22} veiled={false} />
        {/* storm clouds parting */}
        <g fill="#0a141f">
          <g className="ms-clouds-l">
            <ellipse cx="170" cy="52" rx="150" ry="24" filter={`url(#${id}-blur6)`} />
          </g>
          <g className="ms-clouds-r">
            <ellipse cx="560" cy="40" rx="140" ry="22" filter={`url(#${id}-blur6)`} opacity="0.85" />
          </g>
        </g>
        <Hills id={id} />

        {/* the links close, one by one, and a packet starts to breathe */}
        <line className="ms-link ms-link-a" x1="176" y1="222" x2="420" y2="196" stroke={P.green} strokeWidth="1.6" />
        <line className="ms-link ms-link-b" x1="440" y1="196" x2="688" y2="238" stroke={P.green} strokeWidth="1.6" />
        <circle className="ms-pkt" r="3.4" fill={P.amber}>
          <animateMotion dur="2.6s" begin="4.6s" repeatCount="indefinite" path="M 176 218 L 430 192 L 688 234" />
        </circle>

        <LoraNode x={168} y={262} s={0.92} wake={0.7} />
        <LoraNode x={430} y={238} s={1.06} wake={1.5} />
        <LoraNode x={694} y={276} s={0.96} wake={2.7} />

        {/* what kept them alive: sun + battery, quietly in the corner */}
        <g transform="translate(64,300)" opacity="0.85">
          <g stroke={P.amber} strokeWidth="1.5" fill="none">
            <circle r="7" />
            {Array.from({ length: 8 }, (_, i) => {
              const a = (i * 45 * Math.PI) / 180
              return <line key={i} x1={Math.cos(a) * 10} y1={Math.sin(a) * 10} x2={Math.cos(a) * 13} y2={Math.sin(a) * 13} />
            })}
          </g>
          <g transform="translate(30,-6)" stroke={P.green} strokeWidth="1.5" fill="none">
            <rect x="0" y="0" width="24" height="12" rx="2.5" />
            <rect x="25" y="3.5" width="3" height="5" fill={P.green} stroke="none" />
            <rect x="2.5" y="2.5" width="15" height="7" fill={P.green} stroke="none" opacity="0.9" />
          </g>
        </g>
      </g>
      <Vignette id={id} />
    </svg>
  )
}

/** beat key -> its vignette */
export const SCENES = {
  rain: <RainScene />,
  slide: <LandslideScene />,
  dark: <PowerCutScene />,
  tower: <TowerScene />,
  mesh: <MeshScene />,
}
