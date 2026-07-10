import { motion } from "framer-motion";
import {
  Satellite,
  MapPin,
  Sparkles,
  Send,
  CheckCircle2,
  Waves,
  Flame,
  HeartPulse,
  UserSearch,
  Boxes,
  CircleHelp,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { urgencyColor, urgencyLabel, clampUrgency } from "@/lib/urgency";

const CATEGORY_ICON = {
  flood: Waves,
  fire: Flame,
  medical: HeartPulse,
  missing: UserSearch,
  trapped: Boxes,
};

// One SOS in the triage queue. All victim-derived text (english/gist/rationale)
// is rendered as React children => plain text, never dangerouslySetInnerHTML
// (project rule #9: translated/transcribed text is data, not HTML).
export default function SosCard({ record, onAccept, selected, onSelect }) {
  const t = record.triage || {};
  const u = clampUrgency(record.urgency);
  const color = urgencyColor(u);
  const enRoute = record.status === "en route";
  const showOriginal = t.ai && record.english && record.gist && record.english !== record.gist;
  const CatIcon = CATEGORY_ICON[record.category] || CircleHelp;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 14, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ type: "spring", stiffness: 320, damping: 28 }}
    >
      <Card
        onClick={() => onSelect?.(record.id)}
        className={`gap-2 py-3 cursor-pointer transition-shadow ${
          selected ? "ring-2 ring-foreground shadow-md" : "hover:shadow-md"
        } ${enRoute ? "opacity-80" : ""}`}
        style={{ borderLeft: `5px solid ${color}` }}
      >
        <CardContent className="px-3.5">
          <div className="flex items-center gap-2 mb-1.5">
            <Badge className="font-mono text-[10px] font-bold tracking-wide" style={{ background: color }}>
              {urgencyLabel(u)} · {u}
            </Badge>
            <span className="flex items-center gap-1 font-bold uppercase tracking-wide text-[13px]">
              <CatIcon className="size-3.5" style={{ color }} />
              {record.category || "other"}
            </span>
            <span className="ml-auto font-mono text-[10px] text-muted-foreground">
              hop {record.hops ?? 0} · {record.lang || ""}
            </span>
          </div>

          <div className="text-[15px] leading-snug my-1.5">{record.english || record.gist || ""}</div>

          {showOriginal && (
            <div className="text-[12.5px] text-muted-foreground italic leading-snug">
              orig ({record.lang || ""}): {record.gist}
            </div>
          )}

          {record.lat != null && record.lng != null ? (
            <div className="flex items-center gap-1.5 font-mono text-[12px] font-medium mt-1.5">
              <Satellite className="size-3.5 text-muted-foreground" />
              {record.lat.toFixed(5)}, {record.lng.toFixed(5)}
            </div>
          ) : record.locationHint ? (
            <div className="flex items-center gap-1.5 font-mono text-[12px] font-medium mt-1.5">
              <MapPin className="size-3.5 text-muted-foreground" />
              {record.locationHint}
            </div>
          ) : null}

          {t.rationale && (
            <div className="flex items-center gap-1.5 text-[11.5px] text-muted-foreground mt-1">
              <Sparkles className="size-3 shrink-0 text-primary/70" />
              {t.rationale}
              {t.latency_ms ? (
                <span className="font-mono text-primary/80">{t.latency_ms}ms</span>
              ) : null}
            </div>
          )}

          <div className="flex items-center gap-2 mt-2.5">
            {enRoute ? (
              <Badge variant="outline" className="gap-1 text-[#2e7d32] border-[#2e7d32]/40 font-mono text-[10px]">
                <CheckCircle2 /> EN ROUTE
              </Badge>
            ) : (
              <>
                <Badge variant="outline" className="text-primary border-primary/40 font-mono text-[10px]">
                  {(record.status || "new").toUpperCase()}
                </Badge>
                <Button
                  size="sm"
                  className="ml-auto gap-1.5"
                  onClick={(e) => {
                    e.stopPropagation();
                    onAccept(record.id);
                  }}
                >
                  <Send className="size-3.5" /> Dispatch
                </Button>
              </>
            )}
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
