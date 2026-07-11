import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import { MAP_CENTER, MAP_ZOOM, MAP_MIN_ZOOM, MAP_MAX_ZOOM, TILE_STYLE } from "../lib/mapConfig.js";
import { pinColor } from "../lib/urgency.js";

const CAMP_HQ = [77.5921, 12.9767]; // forward camp — Bengaluru city control (Cubbon Park)

// Sector map — real offline vector basemap (Bengaluru PMTiles) with live
// incident beacons following the lifecycle arc (open red → claimed amber →
// cleared green), square sensor glyphs, responder dots, and camp HQ.
export default function MapPanel({ incidents, responders, selectedId, onSelect }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef(new Map()); // key -> maplibregl.Marker

  useEffect(() => {
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: TILE_STYLE,
      center: MAP_CENTER,
      zoom: MAP_ZOOM,
      minZoom: MAP_MIN_ZOOM,
      maxZoom: MAP_MAX_ZOOM,
      attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    // Camp HQ — fixed square marker
    const hq = document.createElement("div");
    hq.style.cssText =
      "width:11px;height:11px;background:#1a1a1a;border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.4)";
    new maplibregl.Marker({ element: hq }).setLngLat(CAMP_HQ).addTo(map);

    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
      markersRef.current.clear();
    };
  }, []);

  // Reconcile incident + responder markers with the snapshot.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const seen = new Set();

    const upsert = (key, lng, lat, build) => {
      seen.add(key);
      let marker = markersRef.current.get(key);
      if (!marker) {
        const el = document.createElement("div");
        marker = new maplibregl.Marker({ element: el }).setLngLat([lng, lat]).addTo(map);
        markersRef.current.set(key, marker);
      } else {
        marker.setLngLat([lng, lat]);
      }
      build(marker.getElement());
    };

    for (const inc of incidents) {
      if (inc.lat == null) continue;
      const isSensorOnly = inc.sensor_only;
      upsert(`inc:${inc.id}`, inc.lng, inc.lat, (el) => {
        const color = pinColor(inc);
        const live = !inc.assigned_to && inc.status !== "resolved" && !isSensorOnly;
        el.className = isSensorOnly ? "" : `sos-marker${live ? " live" : ""}`;
        if (isSensorOnly) {
          el.style.cssText =
            `width:12px;height:12px;background:${color};border:2px solid #fff;cursor:pointer;` +
            "box-shadow:0 1px 4px rgba(0,0,0,.35)"; // square = machine, not human
        } else {
          el.style.background = color;
        }
        el.style.outline = selectedId === inc.id ? "3px solid #1a1a1a" : "none";
        el.style.outlineOffset = "2px";
        el.onclick = (e) => {
          e.stopPropagation();
          onSelect?.(inc.id);
        };
      });
    }

    for (const r of responders) {
      if (r.lat == null) continue;
      upsert(`res:${r.id}`, r.lng, r.lat, (el) => {
        const c = r.status === "available" ? "#2e7d32" : r.status === "on_task" ? "#946200" : "#9e9689";
        el.className = "";
        el.style.cssText =
          `width:9px;height:9px;border-radius:50%;background:${c};border:1.5px solid #fff;` +
          "box-shadow:0 1px 3px rgba(0,0,0,.3)";
        el.title = r.callsign;
      });
    }

    for (const [key, marker] of markersRef.current) {
      if (!seen.has(key)) {
        marker.remove();
        markersRef.current.delete(key);
      }
    }
  }, [incidents, responders, selectedId, onSelect]);

  // Pan to selection.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !selectedId) return;
    const inc = incidents.find((i) => i.id === selectedId);
    if (inc && inc.lat != null) map.easeTo({ center: [inc.lng, inc.lat], duration: 600 });
  }, [selectedId, incidents]);

  return (
    <div className="relative rounded-2xl overflow-hidden shadow-sm bg-card min-h-0">
      <div ref={containerRef} className="h-full w-full" />
      <div className="absolute top-2.5 left-3 z-10 flex items-baseline gap-2">
        <span className="font-display italic font-semibold text-[15px] bg-card/85 backdrop-blur px-2 py-0.5 rounded-md shadow-sm">
          Sector Map
        </span>
        <span className="font-mono text-[9px] tracking-wide text-muted-foreground bg-card/85 backdrop-blur px-1.5 py-0.5 rounded shadow-sm">
          OFFLINE TILES
        </span>
      </div>
      <div className="absolute bottom-2 left-2 z-10 bg-card/90 backdrop-blur rounded-md px-2 py-1.5 font-mono text-[8.5px] leading-[1.7] shadow-sm">
        <span className="inline-block size-2 rounded-full bg-u5 mr-1" />OPEN
        <span className="inline-block size-2 rounded-full bg-[#d9a406] ml-2 mr-1" />CLAIMED
        <span className="inline-block size-2 rounded-full bg-[#2e7d32] ml-2 mr-1" />CLEARED
        <br />
        <span className="inline-block size-2 bg-[#946200] mr-1" />SENSOR
        <span className="inline-block size-2 rounded-full bg-[#2e7d32] ml-2 mr-1" />RESPONDER
        <span className="inline-block size-2 bg-foreground ml-2 mr-1" />CAMP HQ
      </div>
    </div>
  );
}
