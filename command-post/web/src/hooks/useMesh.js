import { useCallback, useEffect, useRef, useState } from "react";

// Live connection to the command-post backend. Mirrors the original vanilla
// dashboard's protocol exactly:
//   WS /ws  -> {kind:"snapshot"|"new"|"update", record(s), ai_enabled}
//   POST /inject, POST /accept/{id}
// The backend is the source of truth; this hook just maintains a local mirror
// of the record map + connection/AI status and re-renders React on change.
export function useMesh() {
  const [records, setRecords] = useState([]); // array, backend-sorted on snapshot; we re-sort on merge
  const [connected, setConnected] = useState(false);
  const [aiEnabled, setAiEnabled] = useState(false);
  const mapRef = useRef(new Map()); // id -> record
  const wsRef = useRef(null);

  const publish = useCallback(() => {
    const list = [...mapRef.current.values()].sort(
      (a, b) => (b.urgency - a.urgency) || (b.ts - a.ts)
    );
    setRecords(list);
  }, []);

  useEffect(() => {
    let closedByUs = false;
    let retry;

    function connect() {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws`);
      wsRef.current = ws;

      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!closedByUs) retry = setTimeout(connect, 1500);
      };
      ws.onerror = () => ws.close();
      ws.onmessage = (ev) => {
        let m;
        try {
          m = JSON.parse(ev.data);
        } catch {
          return; // ignore malformed frames
        }
        if (m.kind === "snapshot") {
          mapRef.current.clear();
          (m.records || []).forEach((r) => mapRef.current.set(r.id, r));
          setAiEnabled(!!m.ai_enabled);
          publish();
        } else if (m.kind === "new" || m.kind === "update") {
          if (m.record) mapRef.current.set(m.record.id, m.record);
          publish();
        }
      };
    }

    connect();
    return () => {
      closedByUs = true;
      clearTimeout(retry);
      wsRef.current?.close();
    };
  }, [publish]);

  const inject = useCallback(() => fetch("/inject", { method: "POST" }), []);
  const accept = useCallback(
    (id) => fetch(`/accept/${encodeURIComponent(id)}`, { method: "POST" }),
    []
  );

  return { records, connected, aiEnabled, inject, accept };
}
