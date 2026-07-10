import { useRef, useState } from "react";
import { Mic, Square, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

// Records the browser mic and posts it to POST /voice_sos, which transcribes
// (IndicConformer) → triages → ingests. The resulting SOS arrives on the
// dashboard through the same WebSocket as any other, so there is nothing to
// wire into the queue here — this only captures audio and shows local feedback.
const LANGS = [
  ["ta", "Tamil"], ["hi", "Hindi"], ["te", "Telugu"],
  ["kn", "Kannada"], ["ml", "Malayalam"], ["gu", "Gujarati"],
];

export default function VoiceRecorder() {
  const [state, setState] = useState("idle"); // idle | recording | working
  const [lang, setLang] = useState("ta");
  const [last, setLast] = useState("");
  const mrRef = useRef(null);
  const chunksRef = useRef([]);

  async function start() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunksRef.current = [];
      mr.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data);
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setState("working");
        const blob = new Blob(chunksRef.current, { type: mr.mimeType || "audio/webm" });
        const fd = new FormData();
        fd.append("audio", blob, "sos.webm");
        fd.append("lang", lang);
        try {
          const res = await fetch("/voice_sos", { method: "POST", body: fd });
          const j = await res.json();
          setLast(j.transcript?.text || (j.status === "no_speech" ? "(no speech)" : "(failed)"));
        } catch {
          setLast("(upload failed)");
        }
        setState("idle");
      };
      mrRef.current = mr;
      mr.start();
      setState("recording");
    } catch {
      setLast("(mic blocked)");
    }
  }

  return (
    <div className="flex items-center gap-2">
      <select
        value={lang}
        onChange={(e) => setLang(e.target.value)}
        disabled={state !== "idle"}
        className="h-8 rounded-md border border-border bg-background px-2 text-[12px] font-mono"
        title="Language spoken in the SOS"
      >
        {LANGS.map(([code, name]) => (
          <option key={code} value={code}>{name}</option>
        ))}
      </select>

      {state === "recording" ? (
        <Button size="sm" variant="destructive" className="gap-1.5" onClick={() => mrRef.current?.stop()}>
          <Square className="size-3.5" /> Stop
        </Button>
      ) : (
        <Button size="sm" variant="outline" className="gap-1.5" disabled={state === "working"} onClick={start}>
          {state === "working" ? <Loader2 className="size-3.5 animate-spin" /> : <Mic className="size-3.5" />}
          {state === "working" ? "Transcribing…" : "Voice SOS"}
        </Button>
      )}

      {last && (
        <span className="max-w-[220px] truncate text-[11px] text-muted-foreground" title={last}>
          {last}
        </span>
      )}
    </div>
  );
}
