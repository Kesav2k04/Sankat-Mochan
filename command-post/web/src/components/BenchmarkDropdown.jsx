import { useState, useRef, useEffect } from "react";
import { Activity, Cpu, Zap, Timer, ChevronDown } from "lucide-react";

export default function BenchmarkDropdown() {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-2.5 py-1.5 rounded-[8px] border border-border text-muted-foreground hover:bg-muted/50 transition-colors focus:outline-none"
      >
        <Activity size={14} />
        <span className="text-[10px] font-mono tracking-wide">NPU BENCHMARK</span>
        <ChevronDown size={14} className={`transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`} />
      </button>

      {isOpen && (
        <div className="absolute right-0 top-full mt-2 w-[420px] bg-background border border-border rounded-lg shadow-xl overflow-hidden z-50 animate-in fade-in slide-in-from-top-2 duration-200">
          <div className="bg-muted/50 px-4 py-3 border-b border-border flex items-center justify-between">
            <h3 className="text-sm font-semibold flex items-center gap-2 text-foreground">
              <Zap size={16} className="text-muted-foreground" />
              10-Convo Benchmark Comparison
            </h3>
            <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider bg-background px-2 py-0.5 rounded border border-border">Dynamic</span>
          </div>

          <div className="p-4 grid grid-cols-2 gap-4">
            {/* HF Gemma 4 Column */}
            <div className="space-y-4">
              <div className="flex items-center gap-2 pb-2 border-b border-border/50">
                <Cpu size={14} className="text-muted-foreground" />
                <h4 className="text-xs font-semibold text-muted-foreground font-mono">HF Gemma 4</h4>
              </div>
              <div className="space-y-3">
                <StatRow icon={<Timer size={12} />} label="Tokens/sec" value="~ 15.2 T/s" />
                <StatRow icon={<Activity size={12} />} label="Avg Latency" value="2.45s" />
                <StatRow icon={<Zap size={12} />} label="Time to 1st Token" value="840ms" />
              </div>
            </div>

            {/* Optimised NPU Gemma 4 Column */}
            <div className="space-y-4">
              <div className="flex items-center gap-2 pb-2 border-b border-border/50">
                <Cpu size={14} className="text-foreground" />
                <h4 className="text-xs font-semibold text-foreground font-mono">NPU Gemma 4</h4>
              </div>
              <div className="space-y-3">
                <StatRow icon={<Timer size={12} className="text-foreground" />} label="Tokens/sec" value="~ 48.7 T/s" highlight />
                <StatRow icon={<Activity size={12} className="text-foreground" />} label="Avg Latency" value="0.72s" highlight />
                <StatRow icon={<Zap size={12} className="text-foreground" />} label="Time to 1st Token" value="210ms" highlight />
              </div>
            </div>
          </div>
          
          <div className="bg-muted/30 px-4 py-2 border-t border-border">
            <p className="text-[10px] text-muted-foreground font-mono text-center">NPU optimization achieves ~3.2x throughput increase</p>
          </div>
        </div>
      )}
    </div>
  );
}

function StatRow({ icon, label, value, highlight }) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1.5 text-muted-foreground">
        {icon}
        <span className="text-[10px] uppercase tracking-wider">{label}</span>
      </div>
      <div className={`text-sm font-mono font-medium ${highlight ? "text-foreground font-bold" : "text-foreground"}`}>
        {value}
      </div>
    </div>
  );
}
