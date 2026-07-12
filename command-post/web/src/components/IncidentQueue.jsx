import { AnimatePresence, motion } from "framer-motion";
import { FlaskConical, MapPinOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { priorityLabel, urgencyColor, statusMeta, fmtWait } from "@/lib/urgency";

function IncidentCard({ inc, selected, onSelect }) {
  const color = urgencyColor(inc.urgency);
  const st = statusMeta(inc.status);
  const resolved = inc.status === "resolved";
  const critical = !resolved && Number(inc.urgency) >= 5;
  return (
    <motion.button
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.97 }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
      onClick={() => onSelect(inc.id)}
      // Calm flat card: severity reads from the P-badge + dot, never a tinted
      // fill. Selection is a single 3px urgency-coloured left rail on a clean
      // white card — a quiet Linear-style indicator, no full outline.
      style={selected ? { borderLeftColor: color, borderLeftWidth: 3 } : undefined}
      className={`relative w-full text-left rounded-[16px] px-4 py-3.5 transition-all duration-150 cursor-pointer border ${
        selected
          ? "bg-selected border-border shadow-md pl-[13px]"
          : "bg-surface border-border shadow-sm hover:shadow-md hover:-translate-y-px"
      } ${resolved ? "opacity-50" : ""}`}
    >
      <div className="flex items-start justify-between mb-2.5 gap-3">
        <div className={`text-[15px] font-semibold leading-snug tracking-tight ${resolved ? "text-foreground/70" : "text-foreground"}`}>
          {inc.headline}
        </div>
        <span
          className="shrink-0 flex items-center gap-1.5 font-mono text-[9px] font-bold px-2 py-1 rounded-[8px] uppercase tracking-widest"
          style={{ color: color, background: `color-mix(in srgb, ${color} 12%, transparent)` }}
        >
          <span className="size-1.5 rounded-full" style={{ background: color }} />
          {priorityLabel(inc.urgency)}
        </span>
      </div>

      <div className="flex items-center gap-2 mb-2.5">
        <span
          className="font-mono text-[9px] font-bold px-2 py-0.5 rounded-[8px] uppercase tracking-widest"
          style={{ color: st.fg, background: st.bg }}
        >
          {st.label}
        </span>
        {inc.sensor_confirmed && (
          <span className="font-mono text-[9px] font-bold tracking-widest uppercase px-2 py-0.5 text-success bg-success/10 rounded-[8px] border border-success/20">
            Sensor
          </span>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2.5 font-mono text-[9.5px] uppercase tracking-widest text-muted-foreground/70 border-t border-border/50 pt-2.5">
        <span className="flex items-center gap-1"><span className="text-foreground/50">WAIT</span> {fmtWait(inc.waited_s)}</span>
        <span className="opacity-30">•</span>
        <span className="flex items-center gap-1">
          {inc.location_hint ? (
            <span className="truncate max-w-[110px]">{inc.location_hint}</span>
          ) : (
            <span className="text-warning/80">NO GPS</span>
          )}
        </span>
      </div>
    </motion.button>
  );
}

// Left column — the AI-ranked incident queue with the location-unknown bucket.
export default function IncidentQueue({ incidents, selectedId, onSelect, onInject }) {
  const located = incidents.filter((i) => i.lat != null);
  const unknown = incidents.filter((i) => i.lat == null);
  const open = incidents.filter((i) => i.status !== "resolved").length;

  return (
    <aside className="flex flex-col min-h-0">
      <div className="flex items-baseline gap-3 mb-6 px-1">
        <h2 className="font-display font-semibold text-[22px] m-0 tracking-tight text-foreground">Incidents</h2>
        <span className="u-label">
          {open} OPEN · AI-RANKED
        </span>
        <span className="ml-auto flex items-center gap-1.5 font-mono text-[10px] text-primary">
          <span className="relative flex size-1.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75 duration-3000"></span>
            <span className="relative inline-flex rounded-full size-1.5 bg-primary"></span>
          </span>
          LIVE
        </span>
      </div>

      <ScrollArea className="flex-1 min-h-0 -mx-1 px-1">
        <div className="flex flex-col gap-4 pb-2">
          {incidents.length === 0 && (
            <div className="flex flex-col items-center gap-3 text-center text-muted-foreground py-16 text-sm">
              {/* Alive waiting state — concentric rings breathe like a mesh listener. */}
              <div className="relative flex items-center justify-center size-16 mb-1">
                <div className="absolute inset-0 rounded-full border border-primary/20 animate-[ping_3s_ease-in-out_infinite]" />
                <div className="absolute inset-3 rounded-full border border-primary/40 animate-[ping_3s_ease-in-out_infinite_0.6s]" />
                <div className="size-2 rounded-full bg-primary breathe" />
              </div>
              <div className="font-mono text-[10.5px] tracking-[0.18em] uppercase text-muted-foreground/80">
                Waiting for the mesh…
              </div>
              <Button size="sm" variant="outline" className="mt-1 gap-1.5" onClick={onInject}>
                <FlaskConical className="size-3.5" /> Inject test SOS
              </Button>
            </div>
          )}
          <AnimatePresence mode="popLayout">
            {located.map((inc) => (
              <IncidentCard key={inc.id} inc={inc} selected={selectedId === inc.id} onSelect={onSelect} />
            ))}
          </AnimatePresence>

          {unknown.length > 0 && (
            <>
              <div className="flex items-center gap-1.5 u-section pt-4 pb-1 px-1">
                <MapPinOff className="size-3" /> LOCATION UNKNOWN · {unknown.length}
              </div>
              <AnimatePresence mode="popLayout">
                {unknown.map((inc) => (
                  <IncidentCard key={inc.id} inc={inc} selected={selectedId === inc.id} onSelect={onSelect} />
                ))}
              </AnimatePresence>
            </>
          )}

          {incidents.length > 0 && (
            <Button size="sm" variant="ghost" className="gap-1.5 text-muted-foreground mt-1" onClick={onInject}>
              <FlaskConical className="size-3.5" /> Inject test SOS
            </Button>
          )}
        </div>
      </ScrollArea>
    </aside>
  );
}
