import { useEffect, useState } from "react";
import { Radio, Cpu, TriangleAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import VoiceRecorder from "./VoiceRecorder.jsx";
import BenchmarkDropdown from "./BenchmarkDropdown.jsx";

// Top masthead — brand + camp identity, live clock, link-state chips.
export default function Masthead({ connected, gatewayConnected, aiEnabled }) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const clock = now.toLocaleTimeString("en-IN", {
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  });

  return (
    <header className="relative z-50 flex items-center gap-6 px-8 py-2.5 bg-card border-b border-border">
      {/* Signal glyph — a small mark that pulses when the console is live. */}
      <span className="relative flex size-2.5 shrink-0" title="Console live">
        <span className="absolute inline-flex h-full w-full rounded-full bg-primary opacity-60 breathe" />
        <span className="relative inline-flex size-2.5 rounded-full bg-primary" />
      </span>

      {/* Identity block — the orphaned clock is docked here as a third line of
          metadata so it reads as system identity, not floating text. */}
      <div>
        <h1 className="font-display font-semibold text-2xl tracking-tighter m-0 text-foreground leading-none">
          Sankat-Mochan
        </h1>
        <div className="u-label mt-1.5">
          Command Post · Wayanad Forward Camp 7
        </div>
        <div className="u-label mt-1 tabular !font-medium !tracking-[0.12em]">
          {clock} IST
        </div>
      </div>

      {/* Right cluster grouped by affordance: config · action · status,
          each separated by a vertical rule so hierarchy reads at a glance. */}
      <div className="ml-auto flex items-center gap-5">
        <BenchmarkDropdown />

        <span className="w-px h-6 bg-border" />

        <VoiceRecorder />

        <span className="w-px h-6 bg-border" />

        <div className="flex items-center gap-2">
          {!gatewayConnected ? (
            <div className="flex items-center gap-1.5 font-mono text-[9px] font-bold tracking-widest px-2.5 py-1.5 bg-critical/10 text-critical rounded-[8px]">
              <TriangleAlert className="size-3.5" />
              NO UPLINK
            </div>
          ) : (
            <div className="flex items-center gap-1.5 font-mono text-[9px] font-bold tracking-widest px-2.5 py-1.5 bg-surface-alt text-muted-foreground rounded-[8px] border border-border">
              <Radio className="size-3.5" />
              UPLINK OK
            </div>
          )}

          {!connected && (
            <div className="font-mono text-[9px] font-bold tracking-widest px-2.5 py-1.5 text-muted-foreground bg-surface-alt rounded-[8px] border border-border">
              RECONNECTING...
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
