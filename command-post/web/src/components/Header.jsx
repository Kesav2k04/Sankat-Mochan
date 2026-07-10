import { Radio, Cpu, Activity } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import VoiceRecorder from "./VoiceRecorder.jsx";

// Top bar — identity + live connection / AI-backend status.
export default function Header({ connected, aiEnabled, activeCount }) {
  return (
    <header className="flex items-center gap-4 px-6 py-3 border-b-2 border-foreground bg-card">
      <div className="flex items-baseline gap-3">
        <h1 className="font-display font-bold text-2xl text-primary m-0 leading-none tracking-tight">
          Sankat-Mochan
        </h1>
        <span className="text-[13px] text-muted-foreground hidden sm:inline">
          Command Post · offline triage
        </span>
      </div>

      <div className="ml-auto flex items-center gap-3 text-[13px]">
        <VoiceRecorder />
        <Separator orientation="vertical" className="h-5" />
        <Badge
          variant="outline"
          className={`gap-1.5 font-mono text-[11px] ${
            connected ? "text-[#2e7d32] border-[#2e7d32]/40" : "text-primary border-primary/40"
          }`}
        >
          <Radio className={connected ? "animate-pulse" : ""} />
          {connected ? "MESH LIVE" : "RECONNECTING"}
        </Badge>

        <Badge
          variant="outline"
          className={`gap-1.5 font-mono text-[11px] ${
            aiEnabled ? "text-[#2e7d32] border-[#2e7d32]/40" : "text-primary border-primary/40"
          }`}
        >
          <Cpu />
          {aiEnabled ? "AI: ON-DEVICE" : "AI: RULE-BASED"}
        </Badge>

        <Separator orientation="vertical" className="h-5" />

        <span className="flex items-center gap-1.5 font-mono font-medium">
          <Activity className="size-4 text-primary" />
          {activeCount} active
        </span>
      </div>
    </header>
  );
}
