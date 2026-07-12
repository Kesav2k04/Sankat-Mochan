import { useEffect, useState } from "react";
import { TriangleAlert } from "lucide-react";

// Bottom status bar — instrumentation at a glance (C13 metrics).
export default function StatusBar({ metrics, gateway, database, voice, aiEnabled, sttReady }) {
  const [, tick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 5000);
    return () => clearInterval(t);
  }, []);

  const m = metrics || {};
  const lastRx = m.last_rx ? Math.max(0, Math.round(Date.now() / 1000 - m.last_rx)) : null;
  const ai = aiEnabled
    ? `AI: QWEN LLM${sttReady ? " + INDICCONFORMER STT" : ""} · ON-DEVICE`
    : "AI: RULE-BASED FALLBACK";

  const hasCritical = m.critical_open > 0;

  const StatusIndicator = ({ label, ok, warn }) => (
    <div className="flex items-center gap-1.5 px-4">
      <span className={`size-1.5 rounded-full ${ok ? "bg-success/50" : warn ? "bg-warning/80" : "bg-destructive/80"}`} />
      <span className="uppercase text-muted-foreground/80">{label}</span>
    </div>
  );

  return (
    <footer className="flex items-center divide-x divide-border/40 px-8 py-2.5 font-mono text-[9px] font-bold tracking-widest text-muted-foreground border-t bg-surface">
      <div className="flex items-center pr-4">
        <StatusIndicator label="LoRa Link" ok={gateway?.connected !== false} />
        <StatusIndicator label="BLE Mesh" ok={gateway?.connected !== false} />
        <StatusIndicator label="AI Engine" ok={aiEnabled && sttReady} warn={aiEnabled && !sttReady} />
        <StatusIndicator label="Database" ok={database?.connected !== false} />
        <StatusIndicator label="GPS" ok={true} />
      </div>
      
      <div className="flex items-center pl-4">
        <span className="px-4">
          LAST PKT <b className="text-foreground ml-1">{lastRx == null ? "—" : lastRx < 60 ? `${lastRx}s AGO` : `${Math.floor(lastRx / 60)}m AGO`}</b>
        </span>
        {m.median_triage_ms != null && (
          <span className="px-4">
            LATENCY <b className="text-foreground ml-1">{m.median_triage_ms}ms</b>
          </span>
        )}
      </div>

      <div className="ml-auto flex items-center pl-4">
        {hasCritical && (
          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-[8px] bg-critical/10 text-critical font-bold tracking-widest">
            <TriangleAlert className="size-3.5" />
            {m.critical_open} CRITICAL OPEN
          </span>
        )}
      </div>
    </footer>
  );
}
