// Sahayak agent tag rendering — mirrors the enum whitelist in intelligence.py.
// Values arrive pre-validated by the server; unknown keys/values render nothing
// (defense in depth). All output is plain text (project rule #9).
const INJ_LABELS = {
  bleed: "bleeding",
  fracture: "fracture",
  burn: "burns",
  breath: "breathing difficulty",
  uncon: "unconscious",
  other: "injured",
};

const HZ_LABELS = {
  water: "rising water",
  fire: "fire",
  collapse: "collapse risk",
  gas: "gas leak",
  electric: "electrical hazard",
};

// -> [{ key, label, tone }] tone: "critical" | "warn" | "info"
export function tagChips(tags) {
  if (!tags) return [];
  const chips = [];
  const c = Number(tags.c);
  if (Number.isInteger(c) && c >= 1 && c <= 99) {
    chips.push({ key: "c", label: c > 1 ? `${c} people` : "1 person", tone: "info" });
  }
  if (INJ_LABELS[tags.inj]) {
    chips.push({ key: "inj", label: INJ_LABELS[tags.inj], tone: "critical" });
  }
  if (tags.trap === "y") chips.push({ key: "trap", label: "trapped", tone: "critical" });
  if (HZ_LABELS[tags.hz]) chips.push({ key: "hz", label: HZ_LABELS[tags.hz], tone: "warn" });
  if (tags.mob === "n") chips.push({ key: "mob", label: "cannot move", tone: "warn" });
  if (typeof tags.lm === "string" && tags.lm) {
    chips.push({ key: "lm", label: `near ${tags.lm.slice(0, 48)}`, tone: "info" });
  }
  return chips;
}

export const TAG_TONES = {
  critical: "text-[#c62828] border-[#c62828]/30 bg-[#c62828]/8",
  warn: "text-[#e65100] border-[#e65100]/30 bg-[#e65100]/8",
  info: "text-muted-foreground border-border bg-background/60",
};
