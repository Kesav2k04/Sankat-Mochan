import { useState } from "react";
import { useMesh } from "./hooks/useMesh.js";
import Header from "./components/Header.jsx";
import MapPanel from "./components/MapPanel.jsx";
import QueuePanel from "./components/QueuePanel.jsx";

// Layout: header on top, then a two-pane body — map (left, fills) + ranked
// triage queue (right, fixed). Selection is shared so clicking a card pans the
// map and clicking a marker highlights the card.
export default function App() {
  const { records, connected, aiEnabled, inject, accept } = useMesh();
  const [selectedId, setSelectedId] = useState(null);

  const activeCount = records.filter((r) => r.status !== "en route").length;

  return (
    <div className="h-full flex flex-col paper-texture">
      <Header connected={connected} aiEnabled={aiEnabled} activeCount={activeCount} />
      <div className="flex-1 flex min-h-0">
        <MapPanel records={records} selectedId={selectedId} onSelect={setSelectedId} />
        <QueuePanel
          records={records}
          onAccept={accept}
          onInject={inject}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
      </div>
    </div>
  );
}
