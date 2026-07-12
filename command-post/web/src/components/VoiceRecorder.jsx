import { useRef, useState } from "react";
import { Mic, Square, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

// Records the browser mic and posts it to POST /voice_sos, which transcribes
// (IndicConformer) → triages → ingests. The resulting SOS arrives on the
// dashboard through the same WebSocket as any other, so there is nothing to
// wire into the queue here — this only captures audio and shows local feedback.
//
// Discipline mirrors the mobile VoiceRecorder.kt: a hard duration cap so a clip
// can never grow past what the server accepts, the mic is always released on
// every exit path (success, error, or failure to start), and a mid-recording
// device error can never leave us stuck "recording" with a hot mic.
const LANGS = [
  ["ta", "Tamil"], ["hi", "Hindi"], ["te", "Telugu"],
  ["kn", "Kannada"], ["ml", "Malayalam"], ["gu", "Gujarati"],
];

// The browser clip travels straight to the server over HTTP (not the LoRa mesh),
// so the 5 s airtime cap of the phone does not apply — but an unbounded blob
// would eventually blow past the server's MAX_BROWSER_AUDIO_BYTES (5 MB) and be
// rejected with no useful feedback. Cap the clip well inside that.
const MAX_SECONDS = 30;

// Prefer a container the server labels correctly (it stores voice_sos as webm).
// Fall back gracefully so an older browser still records with its default.
function pickMimeType() {
  if (typeof MediaRecorder === "undefined") return "";
  const prefs = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"];
  return prefs.find((t) => MediaRecorder.isTypeSupported?.(t)) || "";
}

export default function VoiceRecorder() {
  const [state, setState] = useState("idle"); // idle | recording | working
  const [lang, setLang] = useState("ta");
  const [last, setLast] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const mrRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const capRef = useRef(null);

  // Release every resource we might be holding. Safe to call more than once and
  // from any state — the equivalent of the mobile recorder's release()/delete().
  function cleanup() {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    if (capRef.current) { clearTimeout(capRef.current); capRef.current = null; }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    mrRef.current = null;
  }

  async function start() {
    let stream = null;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = pickMimeType();
      const mr = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      streamRef.current = stream;
      chunksRef.current = [];
      setElapsed(0);

      mr.ondataavailable = (e) => e.data?.size && chunksRef.current.push(e.data);

      // A device error mid-recording (mic yanked, tab backgrounded on some
      // browsers) fires onerror, not onstop — without this we would sit in
      // "recording" forever with the mic live. Tear down and reset.
      mr.onerror = () => {
        cleanup();
        setState("idle");
        setLast("(recording error)");
      };

      mr.onstop = async () => {
        cleanup();
        const type = mr.mimeType || pickMimeType() || "audio/webm";
        const blob = new Blob(chunksRef.current, { type });
        // Stopped before any audio was captured — don't POST a guaranteed 400.
        if (!blob.size) {
          setState("idle");
          setLast("(too short)");
          return;
        }
        setState("working");
        const ext = type.includes("ogg") ? "ogg" : "webm";
        const fd = new FormData();
        fd.append("audio", blob, `sos.${ext}`);
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
      // Flush data every second so a long clip isn't held whole until stop, and
      // some browsers only emit ondataavailable when given a timeslice.
      mr.start(1000);
      setState("recording");

      timerRef.current = setInterval(() => setElapsed((s) => s + 1), 1000);
      // Hard backstop: stop ourselves at the cap even if the operator doesn't.
      capRef.current = setTimeout(() => mrRef.current?.stop(), MAX_SECONDS * 1000);
    } catch {
      // getUserMedia denied, or MediaRecorder construction failed — release the
      // mic if we got as far as opening it, so its indicator doesn't stay lit.
      stream?.getTracks().forEach((t) => t.stop());
      cleanup();
      setState("idle");
      setLast("(mic blocked)");
    }
  }

  return (
    <div className="flex items-center gap-2">
      <select
        value={lang}
        onChange={(e) => setLang(e.target.value)}
        disabled={state !== "idle"}
        className="h-8 rounded-[8px] border border-border bg-background px-2 text-[12px] font-mono"
        title="Language spoken in the SOS"
      >
        {LANGS.map(([code, name]) => (
          <option key={code} value={code}>{name}</option>
        ))}
      </select>

      {state === "recording" ? (
        <Button size="sm" variant="destructive" className="gap-1.5" onClick={() => mrRef.current?.stop()}>
          <Square className="size-3.5" /> Stop {elapsed}s / {MAX_SECONDS}s
        </Button>
      ) : (
        <Button size="sm" className="gap-1.5" disabled={state === "working"} onClick={start}>
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
