import { fmtWait } from "@/lib/urgency";
import { Server, Radio, Cpu, TriangleAlert, Activity } from "lucide-react";

const DOT = { available: "#738a64", on_task: "#c68a2c", offline: "#c9bfae" };

// Merged Resource Status Panel (Responders + Capacity metrics)
export default function ResourceStatusPanel({ responders, capacity, criticalOpen = 0 }) {
  const avail = responders.filter((r) => r.status === "available").length;
  const availClass = avail === 0 && criticalOpen > 0 ? "text-critical" : "text-success";
  const c = capacity || {};

  // Every stat has one structure: label → big number → muted caption. A
  // "total" is shown only as the caption (of N) where one exists — no bare /0.
  const Stat = ({ label, value, caption, tone = "text-foreground" }) => (
    <div>
      <div className="u-label mb-2">{label}</div>
      <div className={`font-display text-[22px] font-semibold tracking-tight leading-none ${tone}`}>{value}</div>
      <div className="u-label !font-medium mt-1.5">{caption}</div>
    </div>
  );

  return (
    <div className="bg-surface-alt rounded-[16px] px-6 py-6 border border-border">
      <div className="flex items-center gap-2 mb-6 pb-4 border-b border-border">
        <Activity className="size-4 text-muted-foreground" />
        <h3 className="font-display font-semibold text-[16px] text-foreground m-0">Resource Status</h3>
      </div>

      {/* Locked 2×2 grid — identical column widths, shared vertical guides. */}
      <div className="grid grid-cols-2 gap-y-6 gap-x-6 mb-8">
        <Stat label="Responders" value={avail} caption={`of ${responders.length}`} tone={availClass} />
        <Stat label="Active Missions" value={c.resolved ?? 0} caption="completed" />
        <Stat label="Backlog" value={c.backlog ?? 0} caption="in queue" tone={c.overwhelmed ? "text-critical" : "text-foreground"} />
        <Stat label="Avg Response" value={c.avg_response_min != null ? c.avg_response_min : "—"} caption="minutes" />
      </div>

      {c.overwhelmed && (
        <div className="flex items-center gap-2 font-mono text-[10px] tracking-widest text-critical font-bold mb-6 bg-critical/10 px-3 py-2 rounded-[8px]">
          <TriangleAlert className="size-4" /> BACKLOG EXCEEDS AVAILABLE
        </div>
      )}

      <div className="u-section mb-4">Active Units</div>

      <div className="flex flex-col gap-2">
        {responders.length === 0 && (
          <div className="u-label !font-medium py-3">
            No units linked via Gateway
          </div>
        )}
        {responders.map((r) => {
          const stale = r.status === "offline" && r.last_seen
            ? fmtWait(Date.now() / 1000 - r.last_seen)
            : null;
          return (
            <div key={r.id} className={`flex items-center gap-3 px-3 py-2 rounded-[8px] bg-card border border-border ${r.status === "offline" ? "opacity-50" : ""}`}>
              <span className="size-2.5 rounded-full shrink-0" style={{ background: DOT[r.status] }} />
              <span className="font-mono text-[12px] font-semibold text-foreground">{r.callsign}</span>
              <span className="ml-auto font-mono text-[9px] tracking-widest uppercase" style={{ color: DOT[r.status] }}>
                {r.status}{stale ? ` ${stale}` : ""}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
