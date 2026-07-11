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
    <header className="relative z-50 flex items-center gap-5 px-6 pt-3 pb-2.5 bg-card border-b">
      {/* Signal glyph — a small clay mark that pulses when the console is live. */}
      <span className="relative flex size-2.5 shrink-0" title="Console live">
        <span className="absolute inline-flex h-full w-full rounded-[2px] bg-brand opacity-60 breathe" />
        <span className="relative inline-flex size-2.5 rounded-[2px] bg-brand" />
      </span>

      <div>
        <h1 className="font-display font-semibold text-[28px] leading-none tracking-[-0.02em] m-0">
          Sankat-Mochan
        </h1>
        <div className="font-mono text-[10px] font-medium tracking-[0.2em] text-muted-foreground mt-1.5">
          COMMAND POST · WAYANAD FORWARD CAMP 7
        </div>
      </div>

      <div className="font-mono text-[13px] font-medium text-foreground/80 ml-2 tabular">{clock} <span className="text-muted-foreground">IST</span></div>

      <div className="ml-auto flex items-center gap-2.5">
        <BenchmarkDropdown />
        <VoiceRecorder />
        <span className="w-px h-5 bg-border" />
        <div className="flex items-center gap-1.5">
          {!gatewayConnected ? (
            <Badge className="gap-1.5 font-mono text-[10px] tracking-wide bg-destructive text-destructive-foreground border-transparent">
              <TriangleAlert className="size-3.5" />
              NO FIELD UPLINK
            </Badge>
          ) : (
            <Badge variant="outline" className="gap-1.5 font-mono text-[10px] tracking-wide text-muted-foreground border-transparent">
              <Radio className="size-3.5" />
              UPLINK OK
            </Badge>
          )}

          {!connected && (
            <Badge variant="outline" className="gap-1.5 font-mono text-[10px] tracking-wide text-muted-foreground border-transparent">
              RECONNECTING...
            </Badge>
          )}
        </div>
      </div>
    </header>
  );
}
