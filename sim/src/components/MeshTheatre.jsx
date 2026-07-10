import { memo, useEffect, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { Protocol } from 'pmtiles'
import { layers, namedFlavor } from '@protomaps/basemaps'
import { NODES, edgeGeoPx, pointOnEdge, edgePath, linkKind } from '../sim/topology.js'

// Real offline basemap — the same Wayanad PMTiles extract the command post
// serves (data © OpenStreetMap contributors, ODbL; rendering MapLibre +
// @protomaps/basemaps, both BSD-3). Nothing touches the network at runtime.
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

/** Everything the demo uses, with margin. */
const FIT = [
  [76.088, 11.662],
  [76.198, 11.72],
]

const URGENCY = { 5: '#d92d20', 4: '#e04f16', 3: '#b98900', 2: '#079455', 1: '#1570ef' }
const PKT_COLOR = {
  SOS: null, // takes the urgency colour
  ACK: '#98a2b3',
  TASK: '#7c3aed',
  ACCEPT: '#079455',
  ACCEPTED: '#079455',
  VOICE: '#0e7490',
  NACK: '#dd2590',
  LOST: '#d92d20',
}
const LINK_COLOR = { ble: '#0e7490', lora: '#b45309', wire: '#7c3aed' }
const STATUS_COLOR = { available: '#079455', proposed: '#b98900', on_task: '#e04f16', 'en route': '#e04f16', 'on-scene': '#0e7490', offline: '#c5ccd3' }

/** The slip zone around the scar hotspot — drawn on the real map, not instead of it. */
const SCAR = [
  [11.7128, 76.0952],
  [11.7112, 76.1022],
  [11.7062, 76.1041],
  [11.7043, 76.0994],
  [11.7066, 76.0944],
  [11.7105, 76.0932],
]

function MeshTheatre({ fast, incidents, focusId, onFocus }) {
  const boxRef = useRef(null)
  const mapRef = useRef(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const map = new maplibregl.Map({
      container: boxRef.current,
      style: STYLE,
      bounds: FIT,
      fitBoundsOptions: { padding: 30 },
      minZoom: 11,
      maxZoom: 16.5,
      maxBounds: [
        [76.03, 11.58],
        [76.24, 11.79],
      ],
      dragRotate: false,
      pitchWithRotate: false,
      attributionControl: { compact: true },
    })
    map.touchZoomRotate.disableRotation()
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right')
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 120 }), 'bottom-left')
    map.on('load', () => setReady(true))
    mapRef.current = map
    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  const map = mapRef.current
  const respById = Object.fromEntries(fast.responders.map((r) => [r.id, r]))
  const nodeOf = (id) => fast.victims[id] ?? respById[id] ?? NODES[id]
  const px = (n) => map.project([n.lng, n.lat])

  // metres -> screen pixels at the current zoom (for the 100 m cluster rings)
  const mpp = ready ? (156543.03392 * Math.cos((11.69 * Math.PI) / 180)) / 2 ** map.getZoom() : 1

  return (
    <div className="theatre">
      <div ref={boxRef} className="basemap" />

      {ready && (
        <svg className="overlay">
          {/* landslide zone */}
          <polygon
            points={SCAR.map(([la, ln]) => {
              const p = px({ lat: la, lng: ln })
              return `${p.x},${p.y}`
            }).join(' ')}
            fill="#d92d20"
            fillOpacity="0.07"
            stroke="#d92d20"
            strokeOpacity="0.35"
            strokeWidth="1.2"
            strokeDasharray="6 5"
          />
          {(() => {
            const p = px({ lat: 11.7135, lng: 76.0975 })
            return <text x={p.x} y={p.y - 6} textAnchor="middle" className="svg-label danger">LANDSLIDE ZONE · NO CELL, NO INTERNET</text>
          })()}

          {/* infrastructure links */}
          {[['P1', 'P2'], ['P2', 'L1'], ['L1', 'G1'], ['G1', 'CP']].map(([a, b]) => {
            const kind = linkKind(a, b)
            const geo = edgeGeoPx(px(NODES[a]), px(NODES[b]), kind)
            const mid = pointOnEdge(geo, 0.5)
            return (
              <g key={`${a}${b}`}>
                <path d={edgePath(geo)} fill="none" stroke={LINK_COLOR[kind]} strokeWidth={kind === 'lora' ? 1.8 : 1.2} strokeOpacity="0.4" strokeDasharray={kind === 'ble' ? '5 6' : kind === 'lora' ? '0' : '2 4'} />
                {kind !== 'wire' && (
                  <text x={mid.x} y={mid.y - 8} textAnchor="middle" className="svg-label" fill={LINK_COLOR[kind]}>
                    {kind === 'lora' ? 'LoRa 865 MHz' : 'BLE'}
                  </text>
                )}
              </g>
            )
          })}

          {/* incident cluster rings — 100 m eps, true to map scale */}
          {incidents
            .filter((i) => !i.noFix && i.state !== 'resolved')
            .map((inc) => {
              const p = px(inc)
              const r = Math.max(14, 100 / mpp + inc.members.length * 3)
              return (
                <g key={inc.id} transform={`translate(${p.x},${p.y})`}>
                  <circle r={r} fill={URGENCY[inc.urgency]} fillOpacity="0.08" stroke={URGENCY[inc.urgency]} strokeOpacity="0.5" strokeWidth="1" strokeDasharray="3 4" />
                  {inc.members.length > 1 && (
                    <text y={-r - 5} textAnchor="middle" className="svg-label" fill={URGENCY[inc.urgency]}>
                      {inc.id} · {inc.members.length} reports
                    </text>
                  )}
                </g>
              )
            })}

          {/* victims */}
          {Object.values(fast.victims).map((v) => {
            const p = px(v)
            const relay = px(NODES[v.relay])
            const isFocus = focusId && focusId.startsWith(v.label)
            const c = URGENCY[v.urgency] ?? '#b98900'
            return (
              <g key={v.id}>
                <path d={`M ${p.x} ${p.y} L ${relay.x} ${relay.y}`} fill="none" stroke="#0e7490" strokeOpacity="0.15" strokeWidth="1" strokeDasharray="4 5" />
                <g transform={`translate(${p.x},${p.y})`} className="clickable" onClick={() => onFocus(`${v.label}-0`)}>
                  {v.noFix && <circle r="13" fill="none" stroke="#98a2b3" strokeWidth="1" strokeDasharray="2 3" />}
                  {isFocus && <circle r="17" fill="none" stroke="#344054" strokeOpacity="0.4" strokeWidth="1" />}
                  <circle r={v.urgency >= 5 ? 6 : 4.5} fill={c} stroke="#fff" strokeWidth="1.2" />
                  <circle r={v.urgency >= 5 ? 6 : 4.5} fill="none" stroke={c} strokeWidth="1">
                    <animate attributeName="r" values="5;16;5" dur="2.4s" repeatCount="indefinite" />
                    <animate attributeName="opacity" values="0.8;0;0.8" dur="2.4s" repeatCount="indefinite" />
                  </circle>
                  {v.noFix && <text y="-19" textAnchor="middle" className="svg-label dim">NO FIX</text>}
                </g>
              </g>
            )
          })}

          {/* fixed infrastructure */}
          {Object.values(NODES).map((n) => {
            const p = px(n)
            const tx = fast.radioTx.find((r) => r.node === n.id)
            return (
              <g key={n.id} transform={`translate(${p.x},${p.y})`}>
                {tx &&
                  [0, 1, 2].map((i) => {
                    const t = (tx.t + i / 3) % 1
                    return <circle key={i} r={10 + t * 70} fill="none" stroke="#b45309" strokeWidth="1.2" opacity={0.45 * (1 - t)} />
                  })}

                {n.kind === 'relay' && <path d="M 0 -9 L 8 -4.5 L 8 4.5 L 0 9 L -8 4.5 L -8 -4.5 Z" fill="#e8f6f9" stroke="#0e7490" strokeWidth="1.5" />}
                {n.kind === 'lora' && (
                  <>
                    <path d="M -9 8 L 0 -10 L 9 8 Z" fill="#fdf1e0" stroke="#b45309" strokeWidth="1.5" />
                    <circle r="2" cy="-10" fill="#b45309" />
                  </>
                )}
                {n.kind === 'gateway' && <rect x="-8" y="-8" width="16" height="16" rx="3" fill="#f3edfd" stroke="#7c3aed" strokeWidth="1.5" />}
                {n.kind === 'cp' && (
                  <>
                    <rect x="-13" y="-11" width="26" height="22" rx="5" fill="#e8f6f9" stroke="#0e7490" strokeWidth="1.6" />
                    <path d="M -6 -2 h12 M -6 3 h8 M -6 -7 h10" stroke="#0e7490" strokeWidth="1.2" opacity="0.7" />
                  </>
                )}

                <text y={n.kind === 'cp' ? 26 : 22} textAnchor="middle" className="svg-label bright">{n.label}</text>
                <text y={n.kind === 'cp' ? 37 : 33} textAnchor="middle" className="svg-label dim">{n.sub}</text>
              </g>
            )
          })}

          {/* responders */}
          {fast.responders.map((r) => {
            const p = px(r)
            const c = STATUS_COLOR[r.status] ?? '#98a2b3'
            return (
              <g key={r.id} transform={`translate(${p.x},${p.y})`} opacity={r.status === 'offline' ? 0.45 : 1}>
                {r.motion && !r.motion.back && <circle r="14" fill={c} fillOpacity="0.12" />}
                <path d="M 0 -8 L 7 6 L 0 2 L -7 6 Z" fill={c} stroke="#fff" strokeWidth="1" />
                <text y="-13" textAnchor="middle" className="svg-label" fill={c}>{r.callsign}</text>
                {r.motion && !r.motion.back && <text y="20" textAnchor="middle" className="svg-label dim">en route</text>}
              </g>
            )
          })}

          {/* node activity pulses */}
          {fast.pulses.map((p) => {
            const n = nodeOf(p.node)
            if (!n) return null
            const { x, y } = px(n)
            const busy = ['triage', 'cluster', 'rank', 'propose'].includes(p.k)
            const c = busy ? '#0e7490' : p.k === 'speak' || p.k === 'stt' ? '#b98900' : '#079455'
            return (
              <g key={p.id} transform={`translate(${x},${y})`}>
                <circle r={14 + p.t * 14} fill="none" stroke={c} strokeWidth="1.4" opacity={0.7 - p.t * 0.6} />
                {busy && (
                  <circle r="22" fill="none" stroke={c} strokeWidth="1.8" strokeDasharray="4 6" opacity="0.7">
                    <animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="1.6s" repeatCount="indefinite" />
                  </circle>
                )}
              </g>
            )
          })}

          {/* packets in flight */}
          {fast.packets.map((p) => {
            const a = nodeOf(p.from)
            const b = nodeOf(p.to)
            if (!a || !b) return null
            const geo = edgeGeoPx(px(a), px(b), p.link)
            const pos = pointOnEdge(geo, p.t)
            const color = PKT_COLOR[p.pkt] ?? URGENCY[p.urgency] ?? '#0e7490'
            if (p.pkt === 'LOST') {
              const o = 1 - p.dying
              return (
                <g key={p.id} transform={`translate(${pos.x},${pos.y})`} opacity={o}>
                  <circle r={4 + p.dying * 10} fill="none" stroke="#d92d20" strokeWidth="1.5" />
                  <path d="M -4 -4 L 4 4 M 4 -4 L -4 4" stroke="#d92d20" strokeWidth="1.6" />
                </g>
              )
            }
            const rad = p.pkt === 'VOICE' ? 2.4 : p.pkt === 'ACK' ? 2 : 3.4
            return (
              <g key={p.id} transform={`translate(${pos.x},${pos.y})`}>
                <circle r={rad * 2.6} fill={color} opacity="0.15" />
                <circle r={rad} fill={color} stroke="#fff" strokeWidth="0.8" />
                {p.attempt ? <text y="-8" textAnchor="middle" className="svg-label" fill="#0e7490">#1</text> : null}
                {p.pkt === 'NACK' && <text y="-8" textAnchor="middle" className="svg-label" fill="#dd2590">NACK</text>}
              </g>
            )
          })}
        </svg>
      )}

      <div className="legend">
        {[
          ['BLE mesh', '#0e7490'],
          ['LoRa', '#b45309'],
          ['Ethernet', '#7c3aed'],
          ['Return path', '#079455'],
          ['Chunk lost', '#d92d20'],
        ].map(([l, c]) => (
          <span key={l}>
            <i style={{ background: c }} />
            {l}
          </span>
        ))}
      </div>
    </div>
  )
}

export default memo(MeshTheatre)
