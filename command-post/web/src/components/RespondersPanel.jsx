import { fmtWait } from "@/lib/urgency";

const DOT = { available: "#4f7a52", on_task: "#b7861d", offline: "#847d6f" };
const LABEL = { available: "AVAILABLE", on_task: "ON TASK", offline: "OFFLINE" };

// C4 responder registry — compact roster with status dots + staleness.
export default function RespondersPanel({ responders, criticalOpen = 0 }) {
  const avail = responders.filter((r) => r.status === "available").length;
  const availClass = avail === 0 && criticalOpen > 0 ? "text-critical font-bold" : "text-muted-foreground";

  return (
    <div className="bg-card rounded-2xl shadow-sm px-4 py-3">
      <div className="flex items-baseline gap-2 mb-2">
        <h3 className="font-display italic font-semibold text-[15px] m-0">Responders</h3>
        <span className={`ml-auto font-mono text-[9.5px] ${availClass}`}>
          {avail}/{responders.length} AVAILABLE
        </span>
      </div>
      <div className="flex flex-col gap-1.5">
        {responders.length === 0 && (
          <div className="flex flex-col items-center justify-center gap-2 py-4">
            <div className="relative flex items-center justify-center size-10">
               <div className="absolute inset-0 rounded-full border border-muted-foreground/30 animate-[ping_2.6s_ease-in-out_infinite]" />
               <div className="size-2 rounded-full bg-muted-foreground breathe" />
            </div>
            <div className="font-mono text-[9.5px] tracking-wide text-muted-foreground text-center">
              Waiting for a responder BLE link from the Pi…
            </div>
          </div>
        )}
        {responders.map((r) => {
          const stale = r.status === "offline" && r.last_seen
            ? fmtWait(Date.now() / 1000 - r.last_seen)
            : null;
          return (
            <div key={r.id} className={`flex items-center gap-2 ${r.status === "offline" ? "opacity-50" : ""}`}>
              <span className="size-2 rounded-full shrink-0" style={{ background: DOT[r.status] }} />
              <span className="font-mono text-[11px] font-semibold">{r.callsign}</span>
              <span className="text-[11px] text-muted-foreground truncate">{r.capability}</span>
              <span className="ml-auto font-mono text-[8.5px] tracking-wide shrink-0" style={{ color: DOT[r.status] }}>
                {LABEL[r.status]}{stale ? ` ${stale}` : ""}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
