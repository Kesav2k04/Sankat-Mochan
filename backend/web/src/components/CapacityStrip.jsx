import { TriangleAlert } from "lucide-react";

// C8 capacity — derived, read-only "are we keeping up?" with the OVERWHELMED flag.
export default function CapacityStrip({ capacity }) {
  const c = capacity || {};
  const cells = [
    ["AVAIL", `${c.available ?? 0}/${c.total ?? 0}`],
    ["BACKLOG", c.backlog ?? 0],
    ["AVG RESP", c.avg_response_min != null ? `${c.avg_response_min}m` : "—"],
    ["RESOLVED", c.resolved ?? 0],
  ];
  return (
    <div className={`rounded-2xl shadow-sm px-4 py-3 transition-colors duration-300 ${
      c.overwhelmed ? "bg-destructive/8 ring-1 ring-destructive/25" : "bg-card"
    }`}>
      {c.overwhelmed && (
        <div className="flex items-center gap-1.5 font-mono text-[9.5px] tracking-[0.1em] text-destructive font-semibold mb-2">
          <TriangleAlert className="size-3" /> OVERWHELMED — BACKLOG EXCEEDS AVAILABLE RESPONDERS
        </div>
      )}
      <div className="grid grid-cols-4 gap-2">
        {cells.map(([k, v]) => (
          <div key={k}>
            <div className="font-mono text-[8.5px] tracking-[0.14em] text-muted-foreground">{k}</div>
            <div className={`font-mono text-[17px] font-semibold ${k === "BACKLOG" && c.overwhelmed ? "text-destructive" : ""}`}>
              {v}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
