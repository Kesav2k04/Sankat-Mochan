import { AnimatePresence } from "framer-motion";
import { FlaskConical, Inbox } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import SosCard from "./SosCard.jsx";

// Right column — the ranked triage queue. Backend already sorts by
// (urgency, ts); the hook keeps that order.
export default function QueuePanel({ records, onAccept, selectedId, onSelect, onInject }) {
  return (
    <aside className="w-[400px] shrink-0 border-l flex flex-col bg-background paper-texture">
      <div className="flex items-center gap-3 px-4 py-3 border-b">
        <h2 className="font-display font-semibold text-lg m-0">Triage queue</h2>
        <Button size="sm" variant="outline" className="ml-auto gap-1.5" onClick={onInject}>
          <FlaskConical className="size-3.5" /> Inject test SOS
        </Button>
      </div>

      <ScrollArea className="flex-1 min-h-0">
        <div className="px-4 py-3 flex flex-col gap-3">
          {records.length === 0 ? (
            <div className="flex flex-col items-center gap-3 text-center text-muted-foreground py-20 text-sm">
              <Inbox className="size-8 opacity-40" />
              No SOS yet — waiting for the mesh…
            </div>
          ) : (
            <AnimatePresence mode="popLayout">
              {records.map((r) => (
                <SosCard
                  key={r.id}
                  record={r}
                  onAccept={onAccept}
                  selected={selectedId === r.id}
                  onSelect={onSelect}
                />
              ))}
            </AnimatePresence>
          )}
        </div>
      </ScrollArea>
    </aside>
  );
}
