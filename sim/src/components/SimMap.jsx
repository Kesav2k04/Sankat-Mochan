import { memo, useEffect, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { Protocol } from 'pmtiles'
import { layers, namedFlavor } from '@protomaps/basemaps'
import { ZONE, OUTPOST, DANGER_SPOT, RANGE_KM } from '../sim/lora.js'

// Real offline basemap — the same Wayanad PMTiles extract the command post
// serves (data © OpenStreetMap contributors, ODbL; MapLibre + @protomaps/basemaps, BSD-3).
const protocol = new Protocol()
maplibregl.addProtocol('pmtiles', protocol.tile)

const flavor = { ...namedFlavor('light'), background: '#eee7d9' }
const STYLE = {
  version: 8,
  glyphs: `${location.origin}/basemaps-assets/fonts/{fontstack}/{range}.pbf`,
  sprite: `${location.origin}/basemaps-assets/sprites/v4/light`,
  sources: {
    protomaps: {
      type: 'vector',
      url: `pmtiles://${location.origin}/wayanad.pmtiles`,
      attribution: '© OpenStreetMap contributors',
    },
  },
  layers: layers('protomaps', flavor, { lang: 'en' }),
}

const RED = '#d92d20'
const AMBER = '#b45309'
const GREEN = '#079455'
const TEAL = '#0e7490'
const GREY = '#98a2b3'

/** The damaged cell tower — the reason nothing else works tonight. */
const TOWER = { lat: 11.679, lng: 76.155 }

/** The landslide scar — a mud streak running down to the danger spot. */
const SCAR = [
  [11.7148, 76.0448],
  [11.7162, 76.0532],
  [11.7085, 76.0602],
  [11.7008, 76.0625],
  [11.6975, 76.0558],
  [11.7062, 76.0472],
]
const RUBBLE = [
  [11.7075, 76.0545],
  [11.7032, 76.0592],
  [11.7118, 76.0505],
]

/** Village lights that die during the blackout beat. */
const VILLAGES = [
  [11.71, 76.1], [11.7, 76.13], [11.695, 76.16], [11.685, 76.09],
  [11.68, 76.12], [11.676, 76.15], [11.665, 76.11], [11.66, 76.14],
  [11.7, 76.075], [11.672, 76.085], [11.692, 76.185], [11.661, 76.172],
]
const LIGHT_STATE = { rain: 'lit', slide: 'lit', dark: 'dying', tower: 'dead' }

function ease(u) {
  return u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2
}

/** A little human figure — victims and rangers are people, not arrows. */
function Person({ c, wave = false }) {
  return (
    <g>
      <circle cy="-7" r="3.1" fill={c} stroke="#fff" strokeWidth="1.1" />
      <path d="M -4.5 7 Q -4.5 -2.5 0 -2.5 Q 4.5 -2.5 4.5 7 Z" fill={c} stroke="#fff" strokeWidth="1.1" />
      {wave && <line x1="4" y1="-4" x2="8.5" y2="-11" stroke={c} strokeWidth="2" strokeLinecap="round" />}
    </g>
  )
}

function SimMap({ phase, nodes, links, path, rangers, run, clock, fx, beatKey, showZone, showTower, showScar, storyVictim, onPlace, onReady }) {
  const boxRef = useRef(null)
  const mapRef = useRef(null)
  const [ready, setReady] = useState(false)
  const [, setCamTick] = useState(0) // re-project the overlay on ANY map movement
  const phaseRef = useRef(phase)
  phaseRef.current = phase
  const placeRef = useRef(onPlace)
  placeRef.current = onPlace
  const readyRef = useRef(onReady)
  readyRef.current = onReady

  useEffect(() => {
    const map = new maplibregl.Map({
      container: boxRef.current,
      style: STYLE,
      bounds: [
        [76.0, 11.57],
        [76.27, 11.8],
      ],
      fitBoundsOptions: { padding: 24 },
      minZoom: 9.5,
      maxZoom: 15.5,
      maxBounds: [
        [75.9, 11.48],
        [76.4, 11.9],
      ],
      dragRotate: false,
      pitchWithRotate: false,
      attributionControl: { compact: true },
    })
    map.touchZoomRotate.disableRotation()
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right')
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 120 }), 'bottom-right')
    map.on('load', () => {
      setReady(true)
      readyRef.current?.(map)
    })
    // keep the SVG overlay glued to the map: any pan/zoom re-projects it
    map.on('move', () => setCamTick((t) => t + 1))
    map.on('click', (e) => {
      if (phaseRef.current !== 'setup') return
      placeRef.current({ lat: e.lngLat.lat, lng: e.lngLat.lng })
    })
    map.getCanvas().style.cursor = ''
    mapRef.current = map
    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  const map = mapRef.current
  const px = (p) => map.project([p.lng, p.lat])
  // km -> screen px by projecting two real points; immune to tile-size conventions.
  const kmToPx = (km) => {
    const a = map.project([ZONE.lng, ZONE.lat])
    const b = map.project([ZONE.lng + km / (111.32 * Math.cos((ZONE.lat * Math.PI) / 180)), ZONE.lat])
    return Math.abs(b.x - a.x)
  }

  // ---- live positions derived from the timeline clock -----------------------
  const packets = []
  const txNodes = new Set()
  let rangerPos = {}
  let victimVisible = false
  let victimAcked = false
  const overheardNow = new Set()
  let taskState = null // 'alerting' | 'accepted'
  let alertLine = null

  if (run) {
    victimVisible = true
    victimAcked = clock >= run.victimAckAt
    for (const r of run.rangers) rangerPos[r.id] = { lat: r.lat, lng: r.lng }
    for (const [rid, tOh] of run.overhear) if (clock >= tOh) overheardNow.add(rid)
    if (clock >= run.task.tAlert) taskState = clock >= run.task.tAccept ? 'accepted' : 'alerting'
    if (clock >= run.task.tAlert && clock <= run.task.tAccept + 1.2) {
      alertLine = { via: run.task.via, rid: run.task.rid, accepted: clock >= run.task.tAccept }
    }

    for (const seg of run.segs) {
      const local = clock - seg.t0
      if (local < 0) continue
      const u = Math.min(1, local / seg.dur)
      if (seg.kind === 'hop' && local <= seg.dur) {
        packets.push({ from: seg.from, to: seg.to, u, pkt: seg.pkt })
        if (seg.from.id !== 'VICTIM') txNodes.add(seg.from)
        else txNodes.add('VICTIM') // the first broadcast, heard all around the spot
      }
      if (seg.kind === 'respond') {
        const e = ease(u)
        rangerPos[seg.ranger] = {
          lat: seg.from.lat + (seg.to.lat - seg.from.lat) * e,
          lng: seg.from.lng + (seg.to.lng - seg.from.lng) * e,
        }
      }
    }
  }

  const PKT = { SOS: RED, DISPATCH: '#7c3aed', ACCEPT: GREEN, ACK: TEAL }

  return (
    <div className={`theatre ${phase === 'setup' ? 'placing' : ''} ${fx?.shake ? 'fx-shake' : ''}`}>
      <div ref={boxRef} className="basemap" />
      {fx?.rain && <div className="fx-rain" />}
      <div className="fx-tint" style={{ opacity: fx?.tint ?? 0 }} />

      {ready && (
        <svg className="overlay">
          {/* spotlight on the victim while they open the phone */}
          {beatKey === 'phone' &&
            (() => {
              const vp = px(DANGER_SPOT)
              return (
                <>
                  <defs>
                    <radialGradient id="spotg">
                      <stop offset="55%" stopColor="#000" />
                      <stop offset="100%" stopColor="#fff" />
                    </radialGradient>
                    <mask id="spot">
                      <rect width="100%" height="100%" fill="#fff" />
                      <circle cx={vp.x} cy={vp.y} r="130" fill="url(#spotg)" />
                    </mask>
                  </defs>
                  <rect width="100%" height="100%" fill="#04101c" opacity="0.42" mask="url(#spot)" className="fade-in" />
                </>
              )
            })()}

          {/* the landslide scar, tumbling down toward the danger spot */}
          {showScar && (
            <g className={`fade-in ${beatKey === 'slide' ? 'scar-live' : ''}`}>
              <polygon
                points={SCAR.map(([la, ln]) => {
                  const p = px({ lat: la, lng: ln })
                  return `${p.x},${p.y}`
                }).join(' ')}
                fill="#6b4226"
                fillOpacity="0.5"
                stroke="#4a2e1a"
                strokeWidth="1.4"
              />
              {RUBBLE.map(([la, ln], i) => {
                const p = px({ lat: la, lng: ln })
                return <circle key={i} cx={p.x} cy={p.y} r={3.4 - i * 0.6} fill="#4a2e1a" className={beatKey === 'slide' ? 'rubble' : ''} style={{ animationDelay: `${i * 0.4}s` }} />
              })}
            </g>
          )}

          {/* village lights — lit, then dying one by one in the blackout */}
          {LIGHT_STATE[beatKey] &&
            VILLAGES.map(([la, ln], i) => {
              const p = px({ lat: la, lng: ln })
              const st = LIGHT_STATE[beatKey]
              const delay = st === 'dying' ? { animationDelay: `${0.5 + i * 0.26}s` } : undefined
              return (
                <g key={i} transform={`translate(${p.x},${p.y})`} className={`vl ${st}`}>
                  <circle r="7.5" className="vl-glow" style={delay} />
                  <circle r="2.6" className="vl-dot" style={delay} />
                </g>
              )
            })}

          {/* the 10 km danger zone */}
          {showZone &&
            (() => {
              const c = px(ZONE)
              const r = kmToPx(ZONE.radiusKm)
              return (
                <g className="fade-in">
                  <circle cx={c.x} cy={c.y} r={r} fill={RED} fillOpacity="0.05" stroke={RED} strokeOpacity="0.55" strokeWidth="1.6" strokeDasharray="10 7" />
                  <text x={c.x} y={c.y - r + 20} textAnchor="middle" className="svg-label danger">
                    DANGER ZONE · {ZONE.radiusKm} km RADIUS · NO CELL, NO INTERNET
                  </text>
                </g>
              )
            })()}

          {/* the damaged cell tower */}
          {showTower &&
            (() => {
              const p = px(TOWER)
              const dying = beatKey === 'tower'
              return (
                <g transform={`translate(${p.x},${p.y})`} className="fade-in">
                  {dying &&
                    [0, 1, 2].map((i) => {
                      const r = 9 + i * 7
                      return (
                        <path
                          key={i}
                          d={`M ${-r} -18 a ${r} ${r} 0 0 1 ${r * 2} 0`}
                          stroke="#5fb3d9"
                          strokeWidth="2"
                          fill="none"
                          className="sig-die"
                          style={{ animationDelay: `${0.9 + i * 0.55}s` }}
                        />
                      )
                    })}
                  <path d="M -7 12 L 0 -14 L 7 12 M -4.5 3 h9 M -3 -5 h6" stroke="#5b6b78" strokeWidth="1.6" fill="none" />
                  <g className={dying ? 'x-in' : ''}>
                    <line x1="-7" y1="-16" x2="7" y2="-2" stroke={RED} strokeWidth="2.6" strokeLinecap="round" />
                    <line x1="7" y1="-16" x2="-7" y2="-2" stroke={RED} strokeWidth="2.6" strokeLinecap="round" />
                  </g>
                  <text y="26" textAnchor="middle" className="svg-label danger">CELL TOWER DOWN</text>
                </g>
              )
            })()}

          {/* the danger spot — where the SOS originates */}
          {showZone &&
            (() => {
              const p = px(DANGER_SPOT)
              return (
                <g transform={`translate(${p.x},${p.y})`} className="fade-in">
                  <circle r="14" fill="none" stroke={RED} strokeWidth="1.2" strokeDasharray="3 4" opacity="0.7" />
                  <path d="M 0 -8 L 7.5 6 L -7.5 6 Z" fill="#fbe9e7" stroke={RED} strokeWidth="1.6" />
                  <text y="3.5" textAnchor="middle" fontSize="9" fontWeight="700" fill={RED}>!</text>
                  <text y="24" textAnchor="middle" className="svg-label danger">DANGER SPOT</text>
                  {phase === 'setup' && <text y="35" textAnchor="middle" className="svg-label dim">SOS originates here</text>}
                </g>
              )
            })()}

          {/* module -> ranger task alert, while the ranger is tapping Accept */}
          {alertLine &&
            (() => {
              const a = px(alertLine.via)
              const r = px(rangerPos[alertLine.rid])
              return (
                <line x1={a.x} y1={a.y} x2={r.x} y2={r.y} stroke={alertLine.accepted ? GREEN : '#e04f16'} strokeWidth="1.6" strokeDasharray="6 5" opacity="0.85">
                  {!alertLine.accepted && <animate attributeName="stroke-dashoffset" values="22;0" dur="0.7s" repeatCount="indefinite" />}
                </line>
              )
            })()}

          {/* link preview only while BUILDING the mesh — during the story and
              the run there are no wires on the map, only travelling signals */}
          {phase === 'setup' &&
            links.map((l) => {
            const a = px(l.a)
            const b = px(l.b)
            const onPath =
              path &&
              path.some((p, k) => k < path.length - 1 && ((path[k] === l.a && path[k + 1] === l.b) || (path[k] === l.b && path[k + 1] === l.a)))
            return (
              <line
                key={`${l.a.lng},${l.a.lat}-${l.b.lng},${l.b.lat}`}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={onPath ? AMBER : GREY}
                strokeWidth={onPath ? 2 : 1}
                strokeOpacity={onPath ? 0.75 : 0.35}
                strokeDasharray={onPath ? '0' : '4 5'}
                className={!onPath && beatKey === 'mesh' ? 'link-march' : ''}
              />
            )
          })}

          {/* LoRa range rings while placing */}
          {phase === 'setup' &&
            nodes.map((n, i) => {
              const p = px(n)
              return <circle key={`rg${i}`} cx={p.x} cy={p.y} r={kmToPx(RANGE_KM)} fill={AMBER} fillOpacity="0.03" stroke={AMBER} strokeOpacity="0.25" strokeWidth="1" strokeDasharray="2 5" />
            })}

          {/* LoRa modules — each pops in with a bounce and a wake-up ring */}
          {nodes.map((n, i) => {
            const p = px(n)
            const tx = txNodes.has(n)
            return (
              <g key={i} transform={`translate(${p.x},${p.y})`}>
                {tx &&
                  [0, 1, 2].map((k) => {
                    const t = ((clock * 0.8) + k / 3) % 1
                    return <circle key={k} r={10 + t * (kmToPx(RANGE_KM) - 10)} fill="none" stroke={AMBER} strokeWidth="1.3" opacity={0.5 * (1 - t)} />
                  })}
                <g className="pop-in">
                  <circle r="9" fill="none" stroke="#37c978" strokeWidth="1.4">
                    <animate attributeName="r" values="9;34" dur="1.4s" repeatCount="1" fill="freeze" />
                    <animate attributeName="opacity" values="0.8;0" dur="1.4s" repeatCount="1" fill="freeze" />
                  </circle>
                  <path d="M -9 8 L 0 -10 L 9 8 Z" fill="#fdf1e0" stroke={AMBER} strokeWidth="1.6" />
                  <circle r="2" cy="-10" fill={AMBER} />
                </g>
                <text y="22" textAnchor="middle" className="svg-label bright">LORA‑{i + 1}</text>
              </g>
            )
          })}

          {/* outpost — outside the zone */}
          {(() => {
            const p = px(OUTPOST)
            const got = run && clock >= run.outpostAt
            return (
              <g transform={`translate(${p.x},${p.y})`}>
                {got && <circle r="20" fill={GREEN} fillOpacity="0.15" />}
                <rect x="-11" y="-10" width="22" height="20" rx="4" fill={got ? '#e5f4ec' : '#fff'} stroke={got ? GREEN : TEAL} strokeWidth="1.8" />
                <path d="M -5 -1 h10 M -5 4 h7 M -5 -6 h9" stroke={got ? GREEN : TEAL} strokeWidth="1.3" opacity="0.8" />
                <text y="26" textAnchor="middle" className="svg-label bright">{OUTPOST.label}</text>
                <text y="37" textAnchor="middle" className="svg-label dim">{got ? 'SOS RECEIVED' : 'outside the zone'}</text>
              </g>
            )
          })()}

          {/* victim — a person at the spot; their first broadcast rings out all around */}
          {(victimVisible || storyVictim) &&
            (() => {
              const p = px(run?.victim ?? DANGER_SPOT)
              const bc = run && txNodes.has('VICTIM')
              return (
                <g transform={`translate(${p.x},${p.y})`} className="fade-in">
                  {/* the moment of the tap: one big shockwave */}
                  {run && clock < 2.4 && (
                    <circle r="8" fill="none" stroke={RED} strokeWidth="2.4">
                      <animate attributeName="r" values="8;90" dur="2.2s" repeatCount="1" fill="freeze" />
                      <animate attributeName="opacity" values="0.9;0" dur="2.2s" repeatCount="1" fill="freeze" />
                    </circle>
                  )}
                  {bc &&
                    [0, 1, 2].map((k) => {
                      const t = (clock * 0.8 + k / 3) % 1
                      return <circle key={k} r={10 + t * (kmToPx(RANGE_KM) - 10)} fill="none" stroke={RED} strokeWidth="1.2" opacity={0.4 * (1 - t)} />
                    })}
                  {!victimAcked && (
                    <circle r="8" fill="none" stroke={RED} strokeWidth="1">
                      <animate attributeName="r" values="8;22;8" dur="2s" repeatCount="indefinite" />
                      <animate attributeName="opacity" values="0.8;0;0.8" dur="2s" repeatCount="indefinite" />
                    </circle>
                  )}
                  <Person c={victimAcked ? GREEN : RED} wave />
                  {victimAcked ? (
                    <text y="-18" textAnchor="middle" className="svg-label" fill={GREEN}>✓ HELP IS ON THE WAY</text>
                  ) : (
                    <text y="-18" textAnchor="middle" className="svg-label danger">{run ? 'SOS' : 'TRAPPED'}</text>
                  )}
                  {storyVictim && !run && <text y="22" textAnchor="middle" className="svg-label dim">opening the app…</text>}
                </g>
              )
            })()}

          {/* rangers — overhear the SOS (awareness), then one is TASKED by the camp */}
          {rangers.map((r) => {
            const pos = rangerPos[r.id] ?? r
            const p = px(pos)
            const moved = Math.abs(pos.lat - r.lat) > 1e-5 || Math.abs(pos.lng - r.lng) > 1e-5
            const home = px(r)
            const isTasked = run && run.task.rid === r.id
            const tasking = isTasked && taskState === 'alerting'
            const accepted = isTasked && taskState === 'accepted'
            const heard = overheardNow.has(r.id)
            const c = accepted ? GREEN : tasking ? '#e04f16' : GREEN
            return (
              <g key={r.id}>
                {/* the walked trail, home -> here */}
                {moved && <line x1={home.x} y1={home.y} x2={p.x} y2={p.y} stroke={c} strokeWidth="1.6" strokeDasharray="3 5" opacity="0.55" />}
                <g transform={`translate(${p.x},${p.y})`}>
                {tasking && (
                  <circle r="13" fill="none" stroke={c} strokeWidth="1.5">
                    <animate attributeName="r" values="8;18;8" dur="1s" repeatCount="indefinite" />
                    <animate attributeName="opacity" values="0.8;0;0.8" dur="1s" repeatCount="indefinite" />
                  </circle>
                )}
                {accepted && <circle r="12" fill={GREEN} fillOpacity="0.14" />}
                <Person c={c} />
                <text y="-16" textAnchor="middle" className="svg-label" fill={c}>
                  {r.label}
                </text>
                  {tasking && <text y="20" textAnchor="middle" className="svg-label danger">TASKED — accepting…</text>}
                  {accepted && <text y="20" textAnchor="middle" className="svg-label" fill={GREEN}>✓ ACCEPTED · responding</text>}
                  {!tasking && !accepted && heard && <text y="20" textAnchor="middle" className="svg-label dim">overheard SOS · monitoring</text>}
                </g>
              </g>
            )
          })}

          {/* packets in flight — SOS up, DISPATCH/ACK down, ACCEPT back up */}
          {packets.map((pk, i) => {
            const a = px(pk.from)
            const b = px(pk.to)
            const at = (u) => ({ x: a.x + (b.x - a.x) * u, y: a.y + (b.y - a.y) * u })
            const { x, y } = at(pk.u)
            const c = PKT[pk.pkt] ?? RED
            return (
              <g key={i}>
                {/* a comet trail behind the packet */}
                {[0.05, 0.1, 0.16].map((d, k) => {
                  const g = at(Math.max(0, pk.u - d))
                  return <circle key={k} cx={g.x} cy={g.y} r={2.6 - k * 0.7} fill={c} opacity={0.34 - k * 0.1} />
                })}
                <g transform={`translate(${x},${y})`}>
                  <circle r="9" fill={c} opacity="0.15" />
                  <circle r="3.6" fill={c} stroke="#fff" strokeWidth="0.9" />
                  <text y="-9" textAnchor="middle" className="svg-label" fill={c}>{pk.pkt}</text>
                </g>
              </g>
            )
          })}
        </svg>
      )}
    </div>
  )
}

export default memo(SimMap)
