import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronUp, ChevronDown } from "lucide-react";
import { fmtClock } from "@/lib/urgency";

// C13 — the explainable AI-activity feed. Collapsed: latest decision as a
// ticker line. Expanded: the scrolling audit log (why for every decision).
export default function ActivityDrawer({ activity }) {
  const [open, setOpen] = useState(false);
  const latest = activity[activity.length - 1];

  return (
    <div className="bg-card rounded-[12px] border border-border overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-3 px-4 py-2.5 cursor-pointer hover:bg-muted/60 transition-colors"
      >
        <span className="u-label shrink-0">
          AI ACTIVITY
        </span>
        {latest && !open && (
          <span className="font-mono text-[11px] truncate text-foreground/80">
            {fmtClock(latest.ts)} — {latest.text}
          </span>
        )}
        <span className="ml-auto flex items-center gap-1 font-mono text-[9px] text-muted-foreground shrink-0">
          {open ? <>COLLAPSE <ChevronDown className="size-3" /></> : <>EXPAND <ChevronUp className="size-3" /></>}
        </span>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: 176 }}
            exit={{ height: 0 }}
            transition={{ duration: 0.22 }}
            className="overflow-y-auto border-t"
          >
            <div className="px-4 py-2 flex flex-col-reverse gap-1">
              {activity.slice(-60).map((a, i) => (
                <div key={`${a.ts}-${i}`} className="font-mono text-[11px] leading-relaxed">
                  <span className="text-muted-foreground">{fmtClock(a.ts)}</span>{" — "}
                  {a.text}
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
