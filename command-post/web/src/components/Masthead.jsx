import { useEffect, useState } from "react";
import { Radio, Cpu, TriangleAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import VoiceRecorder from "./VoiceRecorder.jsx";

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
    <header className="flex items-center gap-5 px-6 pt-3 pb-2.5 bg-card border-b">
      <div>
        <h1 className="font-display font-bold text-[26px] leading-none tracking-tight m-0">
          Sankat-Mochan
        </h1>
        <div className="font-mono text-[10px] tracking-[0.18em] text-muted-foreground mt-1">
          COMMAND POST · WAYANAD FORWARD CAMP 7
        </div>
      </div>

      <div className="font-mono text-[12px] text-muted-foreground ml-2">{clock} IST</div>

      <div className="ml-auto flex items-center gap-2.5">
        <VoiceRecorder />
        <span className="w-px h-5 bg-border" />
        <Badge
          variant="outline"
          className={`gap-1.5 font-mono text-[10px] tracking-wide ${
            connected ? "text-[#2e7d32] border-[#2e7d32]/30" : "text-primary border-primary/40"
          }`}
        >
          <Radio className={connected ? "blink" : ""} />
          {connected ? "COMMAND POST LIVE" : "RECONNECTING"}
        </Badge>
        <Badge
          variant="outline"
          className={`gap-1.5 font-mono text-[10px] tracking-wide ${
            aiEnabled ? "text-[#2e7d32] border-[#2e7d32]/30" : "text-muted-foreground"
          }`}
        >
          <Cpu />
          {aiEnabled ? "AI ON-DEVICE" : "AI RULE-BASED"}
        </Badge>
        <Badge variant="outline" className="font-mono text-[10px] tracking-wide text-muted-foreground">
          OFFLINE TILES
        </Badge>
        <Badge
          className={`gap-1.5 font-mono text-[10px] tracking-wide border ${
            gatewayConnected
              ? "bg-[#2e7d32]/10 text-[#2e7d32] border-[#2e7d32]/25"
              : "bg-primary/10 text-primary border-primary/25"
          }`}
        >
          {gatewayConnected ? <Radio className="blink" /> : <TriangleAlert />}
          {gatewayConnected ? "FIELD UPLINK · LoRa + BT" : "NO FIELD UPLINK"}
        </Badge>
      </div>
    </header>
  );
}
