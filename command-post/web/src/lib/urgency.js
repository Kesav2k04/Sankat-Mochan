// Presentation helpers — single source of truth for the urgency ramp,
// priority chips, and lifecycle status treatment (matches the v2 design).

export const URGENCY_COLOR = {
  5: "#c62828",
  4: "#e64a19",
  3: "#d9a406",
  2: "#7cb342",
  1: "#9e9689",
};

const PRIORITY_LABEL = { 5: "CRITICAL", 4: "HIGH", 3: "MODERATE", 2: "LOW", 1: "LOW" };

export function clampUrgency(u) {
  return Math.max(1, Math.min(5, Number(u) || 3));
}

export function urgencyColor(u) {
  return URGENCY_COLOR[clampUrgency(u)];
}

export function priorityLabel(u) {
  const n = clampUrgency(u);
  return `P${n} ${PRIORITY_LABEL[n]}`;
}

// Lifecycle arc (C9): open red → claimed amber → cleared green.
export const STATUS_META = {
  "new":                { label: "NEW",       fg: "#b23a1e", bg: "rgba(178,58,30,.10)" },
  "triaged":            { label: "TRIAGED",   fg: "#6b6357", bg: "rgba(107,99,87,.12)" },
  "awaiting responder": { label: "AWAITING RESPONDER", fg: "#c62828", bg: "rgba(198,40,40,.12)" },
  "proposed":           { label: "PROPOSED",  fg: "#946200", bg: "rgba(217,164,6,.14)" },
  "assigned":           { label: "ASSIGNED",  fg: "#946200", bg: "rgba(217,164,6,.14)" },
  "en route":           { label: "EN ROUTE",  fg: "#946200", bg: "rgba(217,164,6,.16)" },
  "on-scene":           { label: "ON-SCENE",  fg: "#2e7d32", bg: "rgba(46,125,50,.12)" },
  "resolved":           { label: "RESOLVED",  fg: "#2e7d32", bg: "rgba(46,125,50,.12)" },
};

export function statusMeta(status) {
  return STATUS_META[status] || STATUS_META["new"];
}

// Map pin colour follows the lifecycle arc; open pins use the urgency ramp.
export function pinColor(incident) {
  if (incident.status === "resolved") return "#2e7d32";
  if (["en route", "assigned", "on-scene", "proposed"].includes(incident.status))
    return "#d9a406";
  return urgencyColor(incident.urgency);
}

export function fmtWait(s) {
  const m = Math.floor((s || 0) / 60);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h${String(m % 60).padStart(2, "0")}m`;
}

export function fmtClock(epoch) {
  if (!epoch) return "—";
  return new Date(epoch * 1000).toLocaleTimeString("en-IN", {
    hour: "2-digit", minute: "2-digit", hour12: false,
  });
}
