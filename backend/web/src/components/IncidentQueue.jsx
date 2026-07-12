import { AnimatePresence, motion } from "framer-motion";
import { FlaskConical, Inbox, MapPinOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { priorityLabel, urgencyColor, statusMeta, fmtWait } from "@/lib/urgency";
import { tagChips, TAG_TONES } from "@/lib/tags";

function IncidentCard({ inc, selected, onSelect }) {
  const chips = tagChips(inc.tags);
  const color = urgencyColor(inc.urgency);
  const st = statusMeta(inc.status);
  const resolved = inc.status === "resolved";
  return (
    <motion.button
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.97 }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
      onClick={() => onSelect(inc.id)}
      className={`w-full text-left bg-card rounded-xl px-3.5 py-3 transition-all duration-200 cursor-pointer ${
        selected
          ? "shadow-md ring-1 ring-primary/60"
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
          <Badge variant="outline" className="font-mono text-[9px] px-1.5 py-0 text-[#2e7d32] border-[#2e7d32]/30">
            + SENSOR
          </Badge>
        )}
        {inc.unresponsive && !resolved && (
          <Badge variant="outline" className="font-mono text-[9px] px-1.5 py-0 text-[#c62828] border-[#c62828]/40 bg-[#c62828]/10">
            UNRESPONSIVE
          </Badge>
        )}
        <span className="ml-auto font-mono text-[10px] text-muted-foreground">
          waited {fmtWait(inc.waited_s)}
        </span>
      </div>
      <div className={`text-[13.5px] font-semibold leading-snug ${resolved ? "" : "text-foreground"}`}>
        {inc.headline}
      </div>
      {chips.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1.5">
          {chips.map((chip) => (
            <span
              key={chip.key}
              className={`font-mono text-[9px] px-1.5 py-0.5 rounded border ${TAG_TONES[chip.tone]}`}
            >
              {chip.label}
            </span>
          ))}
        </div>
      )}
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
        <span className="ml-auto flex items-center gap-1 font-mono text-[10px] text-primary">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-primary blink" /> LIVE
        </span>
      </div>

      <ScrollArea className="flex-1 min-h-0 -mx-1 px-1">
        <div className="flex flex-col gap-2 pb-2">
          {incidents.length === 0 && (
            <div className="flex flex-col items-center gap-2 text-center text-muted-foreground py-16 text-sm">
              <Inbox className="size-7 opacity-40" />
              No SOS yet — waiting for the mesh…
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
