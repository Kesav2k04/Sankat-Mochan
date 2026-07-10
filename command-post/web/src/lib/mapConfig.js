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

// Demo area — matches the sample SOS coordinates in the backend (models.py:
// Wayanad, Kerala ~11.685, 76.130). Re-extract wayanad.pmtiles if you move it.
export const MAP_CENTER = [76.131, 11.686]; // [lng, lat] (MapLibre order)
export const MAP_ZOOM = 13;
export const MAP_MIN_ZOOM = 8;
export const MAP_MAX_ZOOM = 16.9; // extract carries data to z15; overzoom is fine

// Protomaps "light" flavor, nudged toward our warm paper palette.
const flavor = { ...namedFlavor("light"), background: "#eee7d9" };

export const TILE_STYLE = {
  version: 8,
  glyphs: `${location.origin}/basemaps-assets/fonts/{fontstack}/{range}.pbf`,
  sprite: `${location.origin}/basemaps-assets/sprites/v4/light`,
  sources: {
    protomaps: {
      type: "vector",
      tiles: [`${location.origin}/vtiles/{z}/{x}/{y}.pbf`],
      minzoom: 0,
      maxzoom: 15,
      bounds: [76.05, 11.6, 76.22, 11.77],
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: layers("protomaps", flavor, { lang: "en" }),
};
