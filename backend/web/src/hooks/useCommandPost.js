import { useCallback, useEffect, useRef, useState } from "react";

// Live connection to the command-post backend (snapshot protocol).
//   WS /ws -> {kind:"snapshot", incidents, responders, capacity, activity,
//              metrics, ai_enabled, stt_ready, gateway}
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
  gateway: { connected: false, queued: 0, last_ack_ms: null },
  database: { connected: false, session_id: null },
  voice: { received: 0, transcribing: 0, failed: 0, last_received_ms: null, last_clip: null },
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
        // Drop the last snapshot the moment the socket closes. A disconnected board
        // is not live, and — critically — when the server is restarted this guarantees
        // the previous run's incidents/responders/logs vanish immediately instead of
        // lingering on screen until (or unless) a reconnect delivers the new, empty
        // session. The fresh backend then repopulates from its blank snapshot.
        setSnap(EMPTY);
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
        // The backend is the single source of truth: every snapshot fully REPLACES
        // local state (never merges). So a killed-and-restarted server — which starts a
        // brand-new empty session — clears the dashboard the instant it reconnects, and
        // stale incidents/voice from the previous run can never linger. `database.session_id`
        // changes each process start; App watches it to drop transient per-session UI state.
        if (m.kind === "snapshot") setSnap(m);
      };
    }

    // Defer the first connect by a tick so React StrictMode's dev-only
    // mount→unmount→remount doesn't open a socket and abort it mid-connect
    // ("WebSocket is closed before the connection is established" console noise).
    // The unmount clears this timer, so exactly ONE socket is ever created.
    // Production (StrictMode stripped) is unaffected.
    const startTimer = setTimeout(connect, 0);
    return () => {
      closedByUs = true;
      clearTimeout(startTimer);
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
