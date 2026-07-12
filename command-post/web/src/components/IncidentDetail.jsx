import { useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  Play, Pause, SatelliteDish, Route, CheckCircle2, Send, TriangleAlert, Undo2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { priorityLabel, urgencyColor, statusMeta, fmtWait, fmtClock } from "@/lib/urgency";

// Deterministic decorative waveform bars (seeded from the report id).
function WaveBars({ seed }) {
  const bars = useMemo(() => {
    let h = 0;
    for (const c of seed) h = (h * 31 + c.charCodeAt(0)) >>> 0;
    return Array.from({ length: 44 }, (_, i) => {
      h = (h * 1103515245 + 12345) >>> 0;
      return 4 + (h % 18);
    });
  }, [seed]);
  return (
    <div className="flex items-center gap-[2px] h-6">
      {bars.map((b, i) => (
        <span key={i} className="w-[3px] rounded-full bg-foreground/30" style={{ height: b }} />
      ))}
    </div>
  );
}

function AudioPlayer({ src, seed }) {
  const ref = useRef(null);
  const [playing, setPlaying] = useState(false);
  return (
    <div className="flex items-center gap-3 bg-background/60 rounded-lg px-3 py-2 mt-2">
      <button
        onClick={() => {
          const a = ref.current;
          if (!a) return;
          playing ? a.pause() : a.play();
        }}
        className="flex items-center justify-center size-8 rounded-full bg-foreground text-background cursor-pointer shrink-0"
      >
        {playing ? <Pause className="size-3.5" /> : <Play className="size-3.5 ml-0.5" />}
      </button>
      <WaveBars seed={seed} />
      <audio ref={ref} src={src} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} />
    </div>
  );
}

function ReportRow({ r }) {
  return (
    <div className="flex items-baseline gap-2.5 py-2">
      <span className="font-mono text-[9px] font-semibold uppercase px-1.5 py-0.5 rounded-[4px] bg-secondary text-secondary-foreground shrink-0">
        {r.lang}
      </span>
      {/* System output — rendered as plain-text blockquote, never literal quotes. */}
      <span className="u-quote text-[13px] leading-snug text-muted-foreground">{r.english}</span>
      <span className="ml-auto font-mono text-[10px] text-muted-foreground shrink-0 tabular">
        {fmtClock(r.received_at)}
      </span>
    </div>
  );
}

// Centre pane — the selected incident: headline, why-rank, corroboration,
// reports in the cluster, and the propose→confirm dispatch block.
export default function IncidentDetail({ incident, responders, onPropose, onAccept, onResolve }) {
  // One shared label-column width — every label/value pair in this panel
  // (AI Assessment, Primary Report meta) starts values at the same x.
  const LABEL_W = "w-28";

  if (!incident) {
    return (
      <section className="bg-card rounded-[12px] border border-border flex flex-col items-center justify-center text-muted-foreground min-h-0">
        <div className="relative flex items-center justify-center size-24 mb-6">
          <div className="absolute inset-0 rounded-full border border-primary/20 animate-[ping_3s_ease-in-out_infinite]" />
          <div className="absolute inset-2 rounded-full border border-primary/40 animate-[ping_3s_ease-in-out_infinite_0.5s]" />
          <div className="absolute inset-4 rounded-full border border-primary/60 animate-[ping_3s_ease-in-out_infinite_1s]" />
          <div className="size-3 rounded-full bg-primary/80 shadow-[0_0_15px_var(--accent)]" />
        </div>
        <div className="font-mono text-[11px] tracking-[0.2em] text-muted-foreground/70 uppercase">
          Waiting for the mesh...
        </div>
      </section>
    );
  }

  const inc = incident;
  const st = statusMeta(inc.status);
  const color = urgencyColor(inc.urgency);
  const primary = inc.reports?.[0];
  const rest = (inc.reports || []).slice(1).filter((r) => !r.is_sensor);
  const sensors = (inc.reports || []).filter((r) => r.is_sensor);
  const assigned = responders.find((r) => r.id === inc.assigned_to);

  return (
    <motion.section
      key={inc.id}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="bg-card rounded-[12px] flex flex-col min-h-0 border border-border"
    >
      <div className="flex items-center gap-3 px-12 pt-8 pb-6 border-b border-border">
        <span className="u-label">
          {inc.id}{inc.location_hint ? ` · ${inc.location_hint}` : ""}
        </span>
        <span className="font-mono text-[9px] font-bold uppercase tracking-widest px-2 py-0.5 rounded-[4px] border border-black/5" style={{ color: st.fg, background: st.bg }}>
          {st.label}
        </span>
        <span className="ml-auto font-mono text-[10.5px] font-bold tracking-widest uppercase" style={{ color }}>
          {priorityLabel(inc.urgency)}
        </span>
      </div>

      <ScrollArea className="flex-1 min-h-0">
        <div className="px-12 pb-12 pt-10 max-w-4xl mx-auto">
          <h2 className="font-display font-bold text-[44px] tracking-[-0.02em] leading-[1.08] mt-0 mb-2 text-foreground max-w-[24ch]">
            {inc.headline}
          </h2>

          <div className="mt-10 mb-12 border-t border-b border-border py-10">
            <h3 className="u-section mb-7">AI Assessment</h3>
            <div className="flex flex-col gap-6">
              <div className="flex items-start gap-8">
                <div className={`${LABEL_W} u-label shrink-0 pt-1`}>Confidence</div>
                <div className="text-[14px] font-medium flex items-center gap-2">
                  <span className={inc.sensor_confirmed ? "text-success" : "text-warning"}>
                    {inc.sensor_confirmed ? "High" : "Medium"}
                  </span>
                  <span className="opacity-40">•</span>
                  <span className="text-foreground">{inc.sensor_confirmed ? "Sensor Verified" : "Pattern Matched"}</span>
                </div>
              </div>
              <div className="flex items-start gap-8">
                <div className={`${LABEL_W} u-label shrink-0 pt-1`}>Priority Rec</div>
                <div className="text-[14px] font-medium flex items-center gap-2">
                  <span className="text-critical">{priorityLabel(inc.urgency)}</span>
                  <span className="opacity-40">•</span>
                  <span className="text-foreground">Immediate Response Required</span>
                </div>
              </div>
              <div className="flex items-start gap-8">
                <div className={`${LABEL_W} u-label shrink-0 pt-1`}>Rationale</div>
                <div className="text-[14px] font-medium text-foreground leading-snug">
                  {inc.why}
                </div>
              </div>
            </div>
          </div>

          {primary && (
            <div className="mb-10">
              <div className="u-section mb-6">Primary Report</div>
              <div className="flex flex-col gap-4">
                <div className="flex items-baseline gap-2">
                  <span className="font-mono text-[9px] font-bold uppercase tracking-widest px-1.5 py-0.5 rounded-[4px] bg-surface-alt border border-border text-foreground">
                    {primary.lang}
                  </span>
                  <span className="u-label !font-medium normal-case">
                    via {primary.origin} · {primary.hops} hops
                  </span>
                </div>
                {/* Primary system output — blockquote, plain text, no literal quotes. */}
                <div className="u-quote font-display text-[18px] leading-snug text-foreground">
                  {primary.gist || primary.english}
                </div>
                {primary.gist && primary.english && primary.gist !== primary.english && (
                  <div className="text-[14px] text-muted-foreground">
                    <span className="u-label block mb-1">Literal Translation</span>
                    {primary.english}
                  </div>
                )}
                {primary.audio && <AudioPlayer src={primary.audio} seed={primary.id} />}
                {primary.voice_transcript && primary.voice_transcript !== primary.gist && (
                  <div className="text-[14px] text-muted-foreground">
                    <span className="u-label block mb-1">Original Transcript</span>
                    {primary.voice_transcript}
                  </div>
                )}
                {primary.voice_english && primary.voice_english !== primary.voice_transcript && (
                  <div className="text-[14px] text-muted-foreground">
                    <span className="u-label block mb-1">Voice (EN)</span>
                    {primary.voice_english}
                  </div>
                )}
              </div>
              <div className="mt-3 flex flex-col divide-y divide-border/60">
                {rest.map((r) => <ReportRow key={r.id} r={r} />)}
              </div>
            </div>
          )}

          {/* dispatch — C5 propose → C6 responder confirms. Flat bordered
              section, same treatment as AI Assessment / Primary Report above —
              no card-in-a-card. Status is carried by a subtle tint + the button
              is simply right-aligned within the block. */}
          <div className="mt-12">
            <div className="u-section mb-5">Dispatch</div>

            {inc.status === "resolved" ? (
              <div className="flex items-center gap-3 rounded-[12px] px-6 py-5 bg-success/10 text-[14px] border border-success/20">
                <CheckCircle2 className="size-5 text-success shrink-0" />
                <span className="text-foreground font-medium">Cleared{assigned ? ` by ${assigned.callsign}` : ""} — sector broadcast sent; new SOS from this area will not be suppressed.</span>
              </div>
            ) : assigned ? (
              <div className="flex items-center gap-4 rounded-[12px] px-6 py-5 bg-warning/10 border border-warning/20">
                <Route className="size-5 text-warning shrink-0" />
                <div className="text-[14px]">
                  <b className="text-foreground">{assigned.callsign}</b> en route — incident locked (no double dispatch).
                  Victims told “help is on the way” in their language.
                </div>
                <Button size="default" variant="outline" className="ml-auto gap-2" onClick={() => onResolve(inc.id)}>
                  <CheckCircle2 className="size-4" /> Mark resolved
                </Button>
              </div>
            ) : inc.status === "awaiting responder" ? (
              <div className="flex items-center gap-4 rounded-[12px] px-6 py-5 bg-destructive/10 border border-destructive/25">
                <TriangleAlert className="size-5 text-destructive shrink-0" />
                <div className="text-[14px] font-semibold text-destructive">
                  AWAITING RESPONDER — none available.
                </div>
                <Button size="default" variant="outline" className="ml-auto gap-2" onClick={() => onPropose(inc.id)}>
                  <Undo2 className="size-4" /> Retry
                </Button>
              </div>
            ) : inc.proposed ? (
              <div className="rounded-[12px] px-6 py-5 bg-surface-alt border border-border">
                <div className="flex items-center gap-4">
                  <div className="text-[14px] text-foreground font-medium">
                    AI proposes: <span className="text-accent">{inc.proposed.callsign}</span>
                    {inc.proposed.distance_km != null
                      ? <span className="text-muted-foreground font-normal"> — nearest available, {inc.proposed.distance_km} km, ETA ~{inc.proposed.eta_min} min</span>
                      : <span className="text-muted-foreground font-normal"> — first available (no GPS on incident)</span>}
                  </div>
                  <Button size="lg" className="ml-auto gap-2 bg-accent hover:bg-accent-dim text-white px-6 text-[15px] font-semibold" onClick={() => onAccept(inc.id)}>
                    <CheckCircle2 className="size-4" /> Responder accepts
                  </Button>
                </div>
                <div className="u-label mt-4">
                  ETA IS APPROX <span className="opacity-40">•</span> STRAIGHT-LINE <span className="opacity-40">•</span> RESPONDER ACCEPTS ON THEIR PHONE
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-6 rounded-[16px] px-8 py-7 bg-surface-alt border border-border">
                <div className="text-[15px] font-medium text-foreground leading-snug">
                  Propose the nearest available responder for this incident.
                </div>
                <Button size="lg" className="ml-auto gap-2.5 bg-accent hover:bg-accent-dim text-white px-8 text-[15px] font-semibold" onClick={() => onPropose(inc.id)}>
                  <Send className="size-4.5" /> Dispatch Now
                </Button>
              </div>
            )}
          </div>

          {/* meta strip — the reference grid: fixed equal columns, shared
              baseline, unified labels. */}
          <div className="grid grid-cols-4 gap-px bg-border rounded-[12px] overflow-hidden mt-12 border border-border">
            {[
              ["RECEIVED", fmtWait(inc.waited_s) + " ago"],
              ["SOURCE", primary ? primary.origin.toUpperCase() : "—"],
              ["MESH PATH", primary ? `${primary.hops} HOPS` : "—"],
              ["LOCATION", inc.lat != null ? `${inc.lat.toFixed(5)}, ${inc.lng.toFixed(5)}` : (inc.location_hint || "UNKNOWN").toUpperCase()],
            ].map(([k, v]) => (
              <div key={k} className="bg-surface-alt px-5 py-4">
                <div className="u-label !text-[9px]">{k}</div>
                <div className="font-mono text-[11px] font-medium mt-2.5 truncate text-foreground tabular">{v}</div>
              </div>
            ))}
          </div>

          {inc.lat == null && (
            <div className="flex items-center gap-2 u-label !font-medium normal-case mt-3">
              <SatelliteDish className="size-3" /> NO GPS — grouped by location hint; not pinned on the map, still dispatchable.
            </div>
          )}
        </div>
      </ScrollArea>
    </motion.section>
  );
}
