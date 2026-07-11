// Presentation helpers — single source of truth for the urgency ramp,
// priority chips, and lifecycle status treatment (matches the v2 design).

// Warm urgency ramp — tuned to sit on the Anthropic paper canvas. Each step is
// distinct at a glance and dark enough to pass AA as chip text on a tinted fill.
export const URGENCY_COLOR = {
  5: "#bd3b2c", // critical — warm brick (matches --critical)
  4: "#c85a30", // high     — burnt clay
  3: "#a8791a", // moderate — amber-gold
  2: "#5f7a46", // low      — olive
  1: "#847d6f", // low      — warm grey
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
  "new":                { label: "NEW",       fg: "#bd3b2c", bg: "rgba(189,59,44,.10)" },
  "triaged":            { label: "TRIAGED",   fg: "#5c584e", bg: "rgba(92,88,78,.12)" },
  "awaiting responder": { label: "AWAITING RESPONDER", fg: "#bd3b2c", bg: "rgba(189,59,44,.12)" },
  "proposed":           { label: "PROPOSED",  fg: "#8a6410", bg: "rgba(183,134,29,.16)" },
  "assigned":           { label: "ASSIGNED",  fg: "#8a6410", bg: "rgba(183,134,29,.16)" },
  "en route":           { label: "EN ROUTE",  fg: "#8a6410", bg: "rgba(183,134,29,.18)" },
  "on-scene":           { label: "ON-SCENE",  fg: "#3d6640", bg: "rgba(79,122,82,.14)" },
  "resolved":           { label: "RESOLVED",  fg: "#3d6640", bg: "rgba(79,122,82,.14)" },
};

export function statusMeta(status) {
  return STATUS_META[status] || STATUS_META["new"];
}

// Map pin colour follows the lifecycle arc; open pins use the urgency ramp.
export function pinColor(incident) {
  if (incident.status === "resolved") return "#4f7a52";
  if (["en route", "assigned", "on-scene", "proposed"].includes(incident.status))
    return "#b7861d";
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
