// Map configuration — FULLY OFFLINE vector basemap.
//
// Basemap data: backend/static/bangalore.pmtiles — a small-area extract of the Protomaps
// v4 OSM build (build.protomaps.com), covering the Bengaluru city box. Data © OpenStreetMap contributors,
// ODbL. Fonts/sprites are vendored under static/basemaps-assets/ (OFL fonts),
// so NOTHING here touches the network at runtime.
//
// Rendering: MapLibre GL + @protomaps/basemaps layer styles (BSD-3). Tiles are
// served as plain z/x/y HTTP by FastAPI (/vtiles), which unpacks the archive
// server-side — no pmtiles:// browser protocol (MapLibre 5.24's worker→main
// relay for custom protocols silently stalled; plain HTTP is bulletproof).
import { layers, namedFlavor } from "@protomaps/basemaps";

// ── Where the map looks ───────────────────────────────────────────────────
// Bengaluru city centre (Cubbon Park / Vidhana Soudha). This MUST sit inside the bundled
// PMTiles archive (static/bangalore.pmtiles covers lng 77.40–77.80, lat 12.80–13.15) and
// over the seeded incidents in models.py — a centre outside the archive bbox opens the map
// on blank space away from every beacon (the "map is blank / broken" report). Keep this
// centre and the incident coordinates inside the same box.
export const MAP_CENTER = [77.5946, 12.9716]; // [lng, lat] (MapLibre order)
export const MAP_ZOOM = 13;
export const MAP_MIN_ZOOM = 10;
export const MAP_MAX_ZOOM = 17; // archive tops out at z15; MapLibre over-zooms vector cleanly

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
// Key names must match @protomaps/basemaps' Flavor interface exactly — unknown
// keys are silently ignored (parks/roads previously kept their default colors
// because of this).
const flavor = {
  ...namedFlavor("light"),
  background: "#f4f3f0",
  earth: "#f4f3f0",
  park_a: "#c8dcb3",
  park_b: "#c8dcb3",
  wood_a: "#c8dcb3",
  wood_b: "#c8dcb3",
  water: "#a9cbf5",
  buildings: "#e3e1df",
  highway: "#fceea7",
  highway_casing_early: "#eab875",
  highway_casing_late: "#eab875",
  major: "#ffffff",
  major_casing_early: "#dcd9d6",
  major_casing_late: "#dcd9d6",
  minor_a: "#ffffff",
  minor_b: "#ffffff",
  minor_casing: "#dcd9d6",
};
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
export const TILE_STYLE = OFFLINE_STYLE;
export { OFFLINE_STYLE, SATELLITE_STYLE };
