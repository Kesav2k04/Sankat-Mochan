#!/usr/bin/env python3
"""
Build an offline Bengaluru raster .mbtiles for the mesh app, with no external tooling.

Tiles are pulled from CARTO's OpenStreetMap-based basemaps, which are free to reuse with
attribution — appropriate for a small, one-off city cache, unlike the main OSM tile server
whose policy discourages bulk downloads. Map data © OpenStreetMap contributors, tiles ©
CARTO. OSM data is ODbL; CARTO basemaps are free-to-use (CLAUDE.md #1: open licence).

The default style is **voyager** — CARTO's colourful, fully-labelled basemap (roads, place
names, POIs and landmarks baked into the raster). It reads like a standard consumer map
("Google-Maps-level") rather than the sparse dark "ops" look of ``dark_all``, which is why a
person can actually pick out landmarks on it offline. Pass ``--style dark_all`` for the old
dark look, or ``--style rastertiles/voyager_labels_under`` etc. for other CARTO variants.

The output is a spec-compliant MBTiles SQLite file (TMS tile_row), which osmdroid's
OfflineTileProvider reads directly. It is written straight into the app's assets so every
install carries the map:

    app/src/main/assets/tiles/bengaluru.mbtiles

Re-run with a wider --maxzoom for more street detail (each extra zoom ~4x the tiles/size).
The in-app map caps zoom at the archive's maxzoom so a pinch never lands on a blank tile —
keep the code caps (OfflineMap.kt / LiveMap.kt) in step with --minzoom/--maxzoom here.
"""
import argparse
import math
import os
import sqlite3
import time
import urllib.request

# Generous box around Bengaluru city (lon/lat).
MIN_LON, MAX_LON = 77.45, 77.75
MIN_LAT, MAX_LAT = 12.83, 13.14

# CARTO basemap styles. Path segment plugged into the tile URL below.
STYLES = {
    "voyager": "rastertiles/voyager",              # colourful + labelled (default, Google-Maps-like)
    "voyager_labels": "rastertiles/voyager_labels_under",
    "positron": "light_all",                       # light + minimal
    "dark_all": "dark_all",                        # dark "ops" look (previous default)
}
# Round-robin subdomains, exactly as CARTO documents, to spread a one-off bulk pull.
SUBDOMAINS = ("a", "b", "c", "d")
USER_AGENT = "SankatMochan-OfflineMesh/1.0 (offline emergency map cache)"
ATTRIBUTION = "© OpenStreetMap contributors, © CARTO"


def deg2tile(lat, lon, z):
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def tile_ranges(z):
    x0, y0 = deg2tile(MAX_LAT, MIN_LON, z)  # top-left
    x1, y1 = deg2tile(MIN_LAT, MAX_LON, z)  # bottom-right
    return range(min(x0, x1), max(x0, x1) + 1), range(min(y0, y1), max(y0, y1) + 1)


def fetch(url, retries=3):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            # A valid PNG starts with the 8-byte signature; anything else (an HTML error
            # page, a 1x1 blank) must not be written into the archive as if it were a tile.
            if data[:4] == b"\x89PNG":
                return data
            last = f"non-PNG response ({len(data)} bytes)"
        except Exception as e:  # noqa: BLE001 — a one-off CLI, log and retry
            last = str(e)
        time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(last or "unknown error")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minzoom", type=int, default=11)
    ap.add_argument("--maxzoom", type=int, default=15)
    ap.add_argument("--style", default="voyager",
                    help="CARTO style: " + ", ".join(STYLES) + " (or a raw CARTO path)")
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(__file__), "..", "app", "src", "main", "assets", "tiles",
        "bengaluru.mbtiles"))
    ap.add_argument("--delay", type=float, default=0.03)
    args = ap.parse_args()

    style_path = STYLES.get(args.style, args.style)
    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    # Write to a temp file and swap in only on success, so a failed/aborted run never
    # leaves a half-built archive shadowing the good one in the app assets.
    tmp = out + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)

    db = sqlite3.connect(tmp)
    db.execute("CREATE TABLE metadata (name text, value text)")
    db.execute("CREATE TABLE tiles (zoom_level integer, tile_column integer, "
               "tile_row integer, tile_data blob)")
    db.execute("CREATE UNIQUE INDEX tile_index on tiles "
               "(zoom_level, tile_column, tile_row)")
    for name, value in [
        ("name", "Bengaluru"),
        ("type", "baselayer"),
        ("version", "1.1"),
        ("description", f"Offline Bengaluru basemap for Sankat-Mochan ({args.style})"),
        ("format", "png"),
        ("minzoom", str(args.minzoom)),
        ("maxzoom", str(args.maxzoom)),
        ("bounds", f"{MIN_LON},{MIN_LAT},{MAX_LON},{MAX_LAT}"),
        ("center", f"{(MIN_LON + MAX_LON) / 2},{(MIN_LAT + MAX_LAT) / 2},{args.minzoom + 2}"),
        ("attribution", ATTRIBUTION),
    ]:
        db.execute("INSERT INTO metadata VALUES (?,?)", (name, value))

    total, ok, fail = 0, 0, 0
    missed = []
    sub_i = 0
    for z in range(args.minzoom, args.maxzoom + 1):
        xs, ys = tile_ranges(z)
        for x in xs:
            for y in ys:
                total += 1
                sub = SUBDOMAINS[sub_i % len(SUBDOMAINS)]
                sub_i += 1
                url = f"https://{sub}.basemaps.cartocdn.com/{style_path}/{z}/{x}/{y}.png"
                try:
                    data = fetch(url)
                except Exception as e:  # noqa: BLE001
                    fail += 1
                    missed.append((z, x, y))
                    print(f"  MISS z{z} {x}/{y}: {e}")
                    continue
                # MBTiles stores rows bottom-up (TMS); XYZ y is top-down.
                tms_y = (2 ** z - 1) - y
                db.execute(
                    "INSERT OR REPLACE INTO tiles VALUES (?,?,?,?)",
                    (z, x, tms_y, sqlite3.Binary(data)),
                )
                ok += 1
                time.sleep(args.delay)
        db.commit()
        print(f"zoom {z}: {ok} tiles so far ({fail} missed)")

    db.commit()
    db.close()

    if ok == 0:
        os.remove(tmp)
        raise SystemExit("No tiles fetched — leaving the existing archive untouched.")

    os.replace(tmp, out)
    size = os.path.getsize(out)
    print(f"\nDone: {ok} tiles ({fail} missed of {total}) -> {out} "
          f"({size / 1e6:.1f} MB), style={args.style}")
    if missed:
        print(f"Missed {len(missed)} tiles (first few: {missed[:5]}). Re-run to fill gaps.")


if __name__ == "__main__":
    main()
