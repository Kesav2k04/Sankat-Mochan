import { useEffect, useState } from "react";

// Bottom status bar — instrumentation at a glance (C13 metrics).
export default function StatusBar({ metrics, aiEnabled, sttReady }) {
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

  return (
    <footer className="flex items-center gap-5 px-6 py-1.5 font-mono text-[10px] tracking-wide text-muted-foreground bg-card border-t">
      <span>PKT RX <b className="text-foreground">{m.pkt_rx ?? 0}</b></span>
      <span>LAST RX {lastRx == null ? "—" : lastRx < 60 ? `${lastRx}s AGO` : `${Math.floor(lastRx / 60)}m AGO`}</span>
      {m.median_triage_ms != null && <span>MEDIAN TRIAGE {m.median_triage_ms}ms</span>}
      <span>{ai}</span>
      <span className={`ml-auto font-semibold ${m.critical_open ? "text-primary" : ""}`}>
        {m.critical_open ?? 0} CRITICAL OPEN
      </span>
    </footer>
  );
}
