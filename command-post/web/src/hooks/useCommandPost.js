import { useCallback, useEffect, useRef, useState } from "react";

// Live connection to the command-post backend (snapshot protocol).
//   WS /ws -> {kind:"snapshot", incidents, responders, capacity, activity,
//              metrics, ai_enabled, stt_ready}
// Actions: POST /inject, /propose/{id}, /accept/{id}, /resolve/{id}.
// The backend is the single source of truth (C6): every action just triggers
// a fresh snapshot broadcast — no client-side state mutation.
const EMPTY = {
  incidents: [],
  responders: [],
  capacity: { available: 0, total: 0, backlog: 0, overwhelmed: false },
  activity: [],
  metrics: {},
  ai_enabled: false,
  stt_ready: false,
};

export function useCommandPost() {
  const [snap, setSnap] = useState(EMPTY);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);

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
          return;
        }
        if (m.kind === "snapshot") setSnap(m);
      };
    }

    connect();
    return () => {
      closedByUs = true;
      clearTimeout(retry);
      wsRef.current?.close();
    };
  }, []);

  const post = useCallback((path) => fetch(path, { method: "POST" }), []);
  return {
    ...snap,
    connected,
    inject: () => post("/inject"),
    propose: (id) => post(`/propose/${encodeURIComponent(id)}`),
    accept: (id) => post(`/accept/${encodeURIComponent(id)}`),
    resolve: (id) => post(`/resolve/${encodeURIComponent(id)}`),
  };
}
