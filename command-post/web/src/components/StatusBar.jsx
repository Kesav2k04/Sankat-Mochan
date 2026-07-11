import { useEffect, useState } from "react";

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

  return (
    <footer className={`flex items-center gap-0 divide-x divide-border px-6 py-1.5 font-mono text-[10px] tracking-wide text-muted-foreground border-t transition-colors duration-500 ${hasCritical ? "bg-critical/10 border-critical/20" : "bg-card"}`}>
      <span className="pr-3">PKT RX <b className="text-foreground">{m.pkt_rx ?? 0}</b></span>
      <span className="px-3">LAST RX {lastRx == null ? "—" : lastRx < 60 ? `${lastRx}s AGO` : `${Math.floor(lastRx / 60)}m AGO`}</span>
      {m.median_triage_ms != null && <span className="px-3">MEDIAN TRIAGE {m.median_triage_ms}ms</span>}
      <span className="px-3">{ai}</span>
      <span className="px-3">VOICE RX <b className="text-foreground">{voice?.received ?? 0}</b></span>
      {voice?.transcribing > 0 && <span className="px-3 text-warning">TRANSCRIBING {voice.transcribing}</span>}
      {voice?.failed > 0 && <span className="px-3 text-critical">VOICE STT FAILED {voice.failed}</span>}
      {(gateway?.voice_inflight > 0 || gateway?.voice_queued > 0) && (
        <span className="px-3 text-warning">
          VOICE {gateway.voice_inflight ?? 0} ASSEMBLING · {gateway.voice_queued ?? 0} QUEUED
        </span>
      )}
      <span className="px-3" title={database?.session_id || ""}>
        DB {database?.connected ? "ON" : "OFF"} · SESSION {database?.session_id?.slice(0, 8) || "—"}
      </span>
      <span className="ml-auto pl-3 flex items-center">
        <span className={`font-semibold px-2 py-0.5 rounded transition-colors ${hasCritical ? "bg-critical text-critical-foreground" : "text-success"}`}>
          {m.critical_open ?? 0} CRITICAL OPEN
        </span>
      </span>
    </footer>
  );
}
