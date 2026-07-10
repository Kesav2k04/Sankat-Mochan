import { fmtWait } from "@/lib/urgency";

const DOT = { available: "#2e7d32", on_task: "#946200", offline: "#9e9689" };
const LABEL = { available: "AVAILABLE", on_task: "ON TASK", offline: "OFFLINE" };

// C4 responder registry — compact roster with status dots + staleness.
export default function RespondersPanel({ responders }) {
  const avail = responders.filter((r) => r.status === "available").length;
  return (
    <div className="bg-card rounded-2xl shadow-sm px-4 py-3">
      <div className="flex items-baseline gap-2 mb-2">
        <h3 className="font-display italic font-semibold text-[15px] m-0">Responders</h3>
        <span className="ml-auto font-mono text-[9.5px] text-muted-foreground">
          {avail}/{responders.length} AVAILABLE
        </span>
      </div>
      <div className="flex flex-col gap-1.5">
        {responders.length === 0 && (
          <div className="font-mono text-[9.5px] text-muted-foreground py-1">
            Waiting for a responder BLE link from the Pi…
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
