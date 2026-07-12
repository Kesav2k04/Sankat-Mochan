import { useEffect, useState } from "react";
import { useCommandPost } from "./hooks/useCommandPost.js";
import Masthead from "./components/Masthead.jsx";
import IncidentQueue from "./components/IncidentQueue.jsx";
import IncidentDetail from "./components/IncidentDetail.jsx";
import MapPanel from "./components/MapPanel.jsx";
import ResourceStatusPanel from "./components/ResourceStatusPanel.jsx";
import ActivityDrawer from "./components/ActivityDrawer.jsx";
import StatusBar from "./components/StatusBar.jsx";

// Layout (v2 design): masthead / [queue | detail | map+roster+capacity] /
// AI-activity drawer / status bar. One screen, no page scroll.
export default function App() {
  const cp = useCommandPost();
  const [selectedId, setSelectedId] = useState(null);

  // Default selection: keep it valid, else top-ranked incident.
  useEffect(() => {
    if (cp.incidents.length === 0) return;
    if (!selectedId || !cp.incidents.some((i) => i.id === selectedId)) {
      setSelectedId(cp.incidents[0].id);
    }
  }, [cp.incidents, selectedId]);

  const selected = cp.incidents.find((i) => i.id === selectedId) || null;

  return (
    <div className="h-full flex flex-col bg-background">
      <Masthead
        connected={cp.connected}
        gatewayConnected={Boolean(cp.gateway?.connected)}
        aiEnabled={cp.ai_enabled}
      />

      <main className="flex-1 min-h-0 grid grid-cols-[280px_minmax(0,1fr)_380px] gap-8 px-8 py-8 max-w-[1920px] mx-auto w-full">
        <IncidentQueue
          incidents={cp.incidents}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onInject={cp.inject}
        />
        <IncidentDetail
          incident={selected}
          responders={cp.responders}
          onPropose={cp.propose}
          onAccept={cp.accept}
          onResolve={cp.resolve}
        />
        <div className="grid grid-rows-[1fr_auto] gap-6 min-h-0">
          <MapPanel
            incidents={cp.incidents}
            responders={cp.responders}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
          <ResourceStatusPanel responders={cp.responders} capacity={cp.capacity} criticalOpen={cp.metrics?.critical_open ?? 0} />
        </div>
      </main>

      <div className="px-8 pb-4">
        <ActivityDrawer activity={cp.activity} />
      </div>

      <StatusBar
        metrics={cp.metrics}
        gateway={cp.gateway}
        database={cp.database}
        voice={cp.voice}
        aiEnabled={cp.ai_enabled}
        sttReady={cp.stt_ready}
      />
    </div>
  );
}
