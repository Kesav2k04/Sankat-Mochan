import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import { MAP_CENTER, MAP_ZOOM, MAP_MIN_ZOOM, MAP_MAX_ZOOM, TILE_STYLE } from "../lib/mapConfig.js";
import { pinColor } from "../lib/urgency.js";

const CAMP_HQ = [76.1310, 11.6820]; // forward camp (the machine this runs on)

// Sector map — real offline vector basemap (Wayanad PMTiles) with live
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
      attributionControl: false,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    // Camp HQ — fixed square marker
    const hq = document.createElement("div");
    hq.style.cssText =
      "width:11px;height:11px;background:#141413;border:2px solid #fbfaf6;box-shadow:0 1px 3px rgba(20,20,19,.4)";
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
        el.style.outline = selectedId === inc.id ? "3px solid #141413" : "none";
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
        const c = r.status === "available" ? "#4f7a52" : r.status === "on_task" ? "#b7861d" : "#847d6f";
        el.className = "";
        el.style.cssText =
          `width:9px;height:9px;border-radius:50%;background:${c};border:1.5px solid var(--border);` +
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
    <div className="relative rounded-[16px] overflow-hidden bg-surface-alt min-h-0 border border-border">
      <div ref={containerRef} className="h-full w-full opacity-90" />

      {/* Title alone reads as the panel heading — no competing status chip. */}
      <div className="absolute top-3 left-3 z-10">
        <span className="font-display font-semibold text-[15px] bg-card/90 backdrop-blur px-3 py-1.5 rounded-[8px] tracking-tight border border-border">
          Sector Map
        </span>
      </div>

      {/* OFFLINE TILES demoted to quiet status/meta language, out of the title row. */}
      <div className="absolute top-3 right-14 z-10">
        <span className="u-label bg-card/90 backdrop-blur px-2.5 py-1.5 rounded-[8px] border border-border">
          Offline Tiles
        </span>
      </div>

      {/* Legend in a fixed strip with defined columns — dots in row 2 line up
          under the dots in row 1. */}
      <div className="absolute bottom-3 left-3 z-10 bg-card/95 backdrop-blur border border-border rounded-[8px] px-4 py-3">
        <div className="grid grid-cols-3 gap-x-5 gap-y-2 u-label">
          <span className="flex items-center gap-1.5"><span className="inline-block size-2 rounded-full bg-critical" />Open</span>
          <span className="flex items-center gap-1.5"><span className="inline-block size-2 rounded-full bg-warning" />Claimed</span>
          <span className="flex items-center gap-1.5"><span className="inline-block size-2 rounded-full bg-success" />Cleared</span>
          <span className="flex items-center gap-1.5"><span className="inline-block size-2 bg-warning" />Sensor</span>
          <span className="flex items-center gap-1.5"><span className="inline-block size-2 rounded-full bg-success" />Responder</span>
          <span className="flex items-center gap-1.5"><span className="inline-block size-2 bg-foreground outline outline-1 outline-background" />Camp HQ</span>
        </div>
      </div>
    </div>
  );
}
