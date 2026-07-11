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
    <div className="flex items-baseline gap-2.5 px-3 py-2 rounded-lg hover:bg-background/70 transition-colors">
      <span className="font-mono text-[9px] font-semibold uppercase px-1.5 py-0.5 rounded bg-secondary text-secondary-foreground shrink-0">
        {r.lang}
      </span>
      <span className="text-[13px] leading-snug">“{r.english}”</span>
      <span className="ml-auto font-mono text-[10px] text-muted-foreground shrink-0">
        {fmtClock(r.received_at)}
      </span>
    </div>
  );
}

// Centre pane — the selected incident: headline, why-rank, corroboration,
// reports in the cluster, and the propose→confirm dispatch block.
export default function IncidentDetail({ incident, responders, onPropose, onAccept, onResolve }) {
  if (!incident) {
    return (
      <section className="bg-card rounded-2xl shadow-sm flex flex-col items-center justify-center text-muted-foreground min-h-0">
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
      className="bg-card rounded-2xl shadow-sm flex flex-col min-h-0"
    >
      <div className="flex items-center gap-2.5 px-6 pt-4">
        <span className="font-mono text-[11px] tracking-[0.12em] text-muted-foreground">
          {inc.id}{inc.location_hint ? ` · ${inc.location_hint.toUpperCase()}` : ""}
        </span>
        <span className="font-mono text-[9px] font-medium px-1.5 py-0.5 rounded" style={{ color: st.fg, background: st.bg }}>
          {st.label}
        </span>
        <span className="ml-auto font-mono text-[11px] font-semibold" style={{ color }}>
          {priorityLabel(inc.urgency)}
        </span>
      </div>

      <ScrollArea className="flex-1 min-h-0">
        <div className="px-6 pb-5">
          <h2 className="font-display font-semibold text-[26px] leading-tight mt-2 mb-1.5">
            {inc.headline}
          </h2>
          <div className="font-mono text-[10.5px] text-muted-foreground tracking-wide">
            WHY THIS RANK — {inc.why}
          </div>

          {inc.sensor_confirmed && (
            <div className="flex items-start gap-2.5 mt-3 rounded-lg px-3.5 py-2.5 bg-success/10 border border-success/20">
              <span className="size-2 rounded-[2px] bg-success mt-1.5 shrink-0" />
              <div className="text-[12.5px] leading-snug">
                <b>Sensor corroborated</b> — {sensors[0] ? `UNO Q sensor (${sensors[0].origin}) agrees with these reports:` : "a fixed sensor agrees with these reports."}
                {sensors[0] ? ` “${sensors[0].english}”. ` : " "}Highest confidence.
              </div>
            </div>
          )}
          {inc.sensor_only && (
            <div className="flex items-start gap-2.5 mt-3 rounded-lg px-3.5 py-2.5 bg-warning/10 border border-warning/25">
              <TriangleAlert className="size-4 text-warning mt-0.5 shrink-0" />
              <div className="text-[12.5px] leading-snug">
                <b>Sensor alert — unconfirmed.</b> No human report yet; treat as
                “possible, investigate”. A matching SOS will promote this incident.
              </div>
            </div>
          )}

          {primary && (
            <div className="mt-4">
              <div className="font-mono text-[10px] tracking-[0.15em] text-muted-foreground mb-2">
                REPORTS IN CLUSTER · {inc.report_count}
              </div>
              <div className="bg-background/60 rounded-xl px-4 py-3">
                <div className="flex items-baseline gap-2">
                  <span className="font-mono text-[9px] font-semibold uppercase px-1.5 py-0.5 rounded bg-secondary text-secondary-foreground">
                    {primary.lang}
                  </span>
                  <span className="ml-auto font-mono text-[10px] text-muted-foreground">
                    via {primary.origin} · {primary.hops} hops · LoRa
                  </span>
                </div>
                <div className="font-display text-[17px] leading-snug mt-1.5">
                  “{primary.gist || primary.english}”
                </div>
                {primary.gist && primary.english && primary.gist !== primary.english && (
                  <div className="text-[13px] text-muted-foreground mt-1">
                    <span className="font-mono text-[9px] tracking-wide">AI ENGLISH · </span>
                    {primary.english}
                  </div>
                )}
                {primary.audio && <AudioPlayer src={primary.audio} seed={primary.id} />}
                {primary.voice_transcript && primary.voice_transcript !== primary.gist && (
                  <div className="text-[13px] text-muted-foreground mt-2">
                    <span className="font-mono text-[9px] tracking-wide">VOICE TRANSCRIPT · </span>
                    {primary.voice_transcript}
                  </div>
                )}
                {/* Faithful English of the recording, so the operator reads what the
                    audio actually says (distinct from typed-text AI ENGLISH above). */}
                {primary.voice_english && primary.voice_english !== primary.voice_transcript && (
                  <div className="text-[13px] text-muted-foreground mt-1">
                    <span className="font-mono text-[9px] tracking-wide">VOICE (EN) · </span>
                    {primary.voice_english}
                  </div>
                )}
                <div className="font-mono text-[9.5px] tracking-wide text-muted-foreground mt-2">
                  {primary.ai
                    ? `AUTO-TRANSLATED ${primary.lang.toUpperCase()} → ENGLISH · ON-DEVICE · ${primary.latency_ms}ms`
                    : "SELF-REPORTED (NO AI BACKEND)"}
                </div>
              </div>
              <div className="mt-1.5 flex flex-col">
                {rest.map((r) => <ReportRow key={r.id} r={r} />)}
              </div>
            </div>
          )}

          {/* dispatch — C5 propose → C6 responder confirms */}
          <div className="mt-4">
            <div className="font-mono text-[10px] tracking-[0.15em] text-muted-foreground mb-2">DISPATCH</div>

            {inc.status === "resolved" ? (
              <div className="flex items-center gap-2 rounded-xl px-4 py-3 bg-success/10 text-[13px]">
                <CheckCircle2 className="size-4 text-success" />
                Cleared{assigned ? ` by ${assigned.callsign}` : ""} — sector broadcast sent; new SOS from this area will not be suppressed.
              </div>
            ) : assigned ? (
              <div className="flex items-center gap-3 rounded-xl px-4 py-3 bg-warning/10">
                <Route className="size-4 text-warning" />
                <div className="text-[13px]">
                  <b>{assigned.callsign}</b> en route — incident locked (no double dispatch).
                  Victims told “help is on the way” in their language.
                </div>
                <Button size="sm" variant="outline" className="ml-auto gap-1.5" onClick={() => onResolve(inc.id)}>
                  <CheckCircle2 className="size-3.5" /> Mark resolved
                </Button>
              </div>
            ) : inc.status === "awaiting responder" ? (
              <div className="flex items-center gap-3 rounded-xl px-4 py-3 bg-destructive/10 border border-destructive/25">
                <TriangleAlert className="size-4 text-destructive" />
                <div className="text-[13px] font-semibold text-destructive">
                  AWAITING RESPONDER — none available.
                </div>
                <Button size="sm" variant="outline" className="ml-auto gap-1.5" onClick={() => onPropose(inc.id)}>
                  <Undo2 className="size-3.5" /> Retry
                </Button>
              </div>
            ) : inc.proposed ? (
              <div className="rounded-xl px-4 py-3 bg-background/70">
                <div className="flex items-center gap-3">
                  <div className="text-[13.5px]">
                    <b>AI proposes: {inc.proposed.callsign}</b>
                    {inc.proposed.distance_km != null
                      ? <> — nearest available, {inc.proposed.distance_km} km, ETA ~{inc.proposed.eta_min} min</>
                      : <> — first available (no GPS on incident)</>}
                  </div>
                  <Button size="sm" className="ml-auto gap-1.5" onClick={() => onAccept(inc.id)}>
                    <CheckCircle2 className="size-3.5" /> Responder accepts
                  </Button>
                </div>
                <div className="font-mono text-[9.5px] tracking-wide text-muted-foreground mt-1.5">
                  ETA IS APPROX · STRAIGHT-LINE · RESPONDER ACCEPTS ON THEIR PHONE
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-3 rounded-xl px-4 py-3 bg-background/70">
                <div className="text-[13px] text-muted-foreground">
                  Propose the nearest available responder for this incident.
                </div>
                <Button size="sm" className="ml-auto gap-1.5" onClick={() => onPropose(inc.id)}>
                  <Send className="size-3.5" /> Send proposal
                </Button>
              </div>
            )}
          </div>

          {/* meta strip */}
          <div className="grid grid-cols-4 gap-px bg-border rounded-lg overflow-hidden mt-4">
            {[
              ["RECEIVED", fmtWait(inc.waited_s) + " ago"],
              ["SOURCE", primary ? primary.origin.toUpperCase() : "—"],
              ["MESH PATH", primary ? `${primary.hops} HOPS · LoRa` : "—"],
              ["LOCATION", inc.lat != null ? `${inc.lat.toFixed(5)}, ${inc.lng.toFixed(5)}` : (inc.location_hint || "UNKNOWN").toUpperCase()],
            ].map(([k, v]) => (
              <div key={k} className="bg-card px-3 py-2">
                <div className="font-mono text-[8.5px] tracking-[0.15em] text-muted-foreground">{k}</div>
                <div className="font-mono text-[11.5px] mt-0.5 truncate">{v}</div>
              </div>
            ))}
          </div>

          {inc.lat == null && (
            <div className="flex items-center gap-2 font-mono text-[10px] text-muted-foreground mt-2">
              <SatelliteDish className="size-3" /> NO GPS — grouped by location hint; not pinned on the map, still dispatchable.
            </div>
          )}
        </div>
      </ScrollArea>
    </motion.section>
  );
}
