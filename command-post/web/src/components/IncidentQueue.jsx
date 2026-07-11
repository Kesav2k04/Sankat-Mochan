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
      initial={{ opacity: 0, y: 10, boxShadow: "0 0 0 4px var(--accent)" }}
      animate={{ opacity: 1, y: 0, boxShadow: "0 0 0 0px var(--accent)" }}
      exit={{ opacity: 0, scale: 0.97 }}
      transition={{
        type: "spring", stiffness: 300, damping: 30,
        boxShadow: { duration: 1.5, ease: "easeOut" }
      }}
      onClick={() => onSelect(inc.id)}
      // Left rail is keyed to urgency; a live critical also glows on its ring.
      style={{ borderLeft: `3px solid ${resolved ? "var(--border)" : color}` }}
      className={`w-full text-left rounded-xl pl-3 pr-3.5 py-3 transition-all duration-200 cursor-pointer ${
        critical ? "bg-critical/[0.06]" : "bg-card"
      } ${
        selected
          ? "shadow-md ring-1 ring-primary/60"
          : critical
          ? "shadow-sm hover:shadow-md ring-1 ring-critical/25"
          : "shadow-sm hover:shadow-md ring-1 ring-transparent"
      } ${resolved ? "opacity-55" : ""}`}
    >
      <div className="flex items-center gap-1.5 mb-1">
        <span
          className="font-mono text-[10px] font-semibold px-1.5 py-0.5 rounded"
          style={{ color, background: `color-mix(in srgb, ${color} 12%, transparent)` }}
        >
          {priorityLabel(inc.urgency)}
        </span>
        <span
          className="font-mono text-[9px] font-medium px-1.5 py-0.5 rounded"
          style={{ color: st.fg, background: st.bg }}
        >
          {st.label}
        </span>
        {inc.sensor_confirmed && (
          <Badge variant="outline" className="font-mono text-[9px] px-1.5 py-0 text-success border-success/30">
            + SENSOR
          </Badge>
        )}
        <span className="ml-auto font-mono text-[10px] text-muted-foreground">
          waited {fmtWait(inc.waited_s)}
        </span>
      </div>
      <div className={`text-[13.5px] font-semibold leading-snug ${resolved ? "" : "text-foreground"}`}>
        {inc.headline}
      </div>
      <div className="font-mono text-[10px] text-muted-foreground mt-1 truncate">
        {inc.why}
        {inc.location_hint ? ` · ${inc.location_hint.toUpperCase()}` : ""}
        {inc.lat == null ? " · NO GPS" : ""}
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
      <div className="flex items-baseline gap-2 px-1 pb-2">
        <h2 className="font-display italic font-semibold text-xl m-0">Incidents</h2>
        <span className="font-mono text-[10px] tracking-wide text-muted-foreground">
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
        <div className="flex flex-col gap-2 pb-2">
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
              <div className="flex items-center gap-1.5 font-mono text-[10px] tracking-[0.15em] text-muted-foreground pt-2 px-1">
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
