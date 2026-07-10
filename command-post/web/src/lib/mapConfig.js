// Map configuration — FULLY OFFLINE vector basemap.
//
// Basemap data: static/wayanad.pmtiles — a small-area extract of the Protomaps
// OSM build, produced with the officially supported `pmtiles extract` CLI
// (https://docs.protomaps.com/pmtiles/cli). Data © OpenStreetMap contributors,
// ODbL. Fonts/sprites are vendored under static/basemaps-assets/ (OFL fonts),
// so NOTHING here touches the network at runtime.
//
// Rendering: MapLibre GL + @protomaps/basemaps layer styles (BSD-3). Tiles are
// served as plain z/x/y HTTP by FastAPI (/vtiles), which unpacks the archive
// server-side — no pmtiles:// browser protocol (MapLibre 5.24's worker→main
// relay for custom protocols silently stalled; plain HTTP is bulletproof).
import { layers, namedFlavor } from "@protomaps/basemaps";

// ── Where the map looks ───────────────────────────────────────────────────
// Bangalore (dev/testing). Real SOS from phones in the city will pin correctly;
// city-wide zoom covers whichever neighbourhood you're in.
export const MAP_CENTER = [77.5946, 12.9716]; // [lng, lat] (MapLibre order)
export const MAP_ZOOM = 12;
export const MAP_MIN_ZOOM = 8;
export const MAP_MAX_ZOOM = 18;

// ── DEV basemaps: CARTO styled vector maps (no API key; need internet) ──
// Swap the exported style below to change the look.
const CARTO = {
  voyager: "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json",       // clean + colorful (default)
  positron: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",     // light + minimal
  darkMatter: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",// dark "ops" look
};

// Satellite imagery (Esri World Imagery, no key) — dramatic real terrain/buildings.
const SATELLITE_STYLE = {
  version: 8,
  sources: {
    sat: {
      type: "raster",
      tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
      tileSize: 256,
      maxzoom: 19,
      attribution: "Imagery © Esri",
    },
  },
  layers: [{ id: "sat", type: "raster", source: "sat" }],
};

// ── VENUE basemap: fully offline vector from static/*.pmtiles (no network) ──
// To go offline for the demo: regenerate a .pmtiles for your area (pmtiles
// extract), point /vtiles at it, and set `TILE_STYLE = OFFLINE_STYLE` below.
const flavor = { ...namedFlavor("light"), background: "#eee7d9" };
const OFFLINE_STYLE = {
  version: 8,
  glyphs: `${location.origin}/basemaps-assets/fonts/{fontstack}/{range}.pbf`,
  sprite: `${location.origin}/basemaps-assets/sprites/v4/light`,
  sources: {
    protomaps: {
      type: "vector",
      tiles: [`${location.origin}/vtiles/{z}/{x}/{y}.pbf`],
      minzoom: 0,
      maxzoom: 15,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: layers("protomaps", flavor, { lang: "en" }),
};

// DEV → CARTO Voyager (Bangalore). Alternatives: CARTO.positron, CARTO.darkMatter,
// SATELLITE_STYLE — or OFFLINE_STYLE for the no-internet venue demo.
export const TILE_STYLE = CARTO.voyager;
export { OFFLINE_STYLE, SATELLITE_STYLE };
