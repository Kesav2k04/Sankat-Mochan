#!/usr/bin/env python3
"""
Build an offline Bengaluru raster .mbtiles for the mesh app, with no external tooling.

Tiles are pulled from CARTO's OpenStreetMap-based basemaps (dark_all), which are free to
reuse with attribution - appropriate for a small, one-off city cache, unlike the main OSM
tile server whose policy discourages bulk downloads. Map data © OpenStreetMap contributors,
tiles © CARTO. OSM data is ODbL; CARTO basemaps are free-to-use (CLAUDE.md #1: open licence).

The output is a spec-compliant MBTiles SQLite file (TMS tile_row), which osmdroid's
OfflineTileProvider reads directly. It is written straight into the app's assets so every
install carries the map:

    app/src/main/assets/tiles/bengaluru.mbtiles

Re-run with a wider --maxzoom for more street detail (each extra zoom ~4x the tiles/size).
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

TILE_URL = "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"
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


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minzoom", type=int, default=10)
    ap.add_argument("--maxzoom", type=int, default=14)
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(__file__), "..", "app", "src", "main", "assets", "tiles",
        "bengaluru.mbtiles"))
    ap.add_argument("--delay", type=float, default=0.05)
    args = ap.parse_args()

    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if os.path.exists(out):
        os.remove(out)

    db = sqlite3.connect(out)
    db.execute("CREATE TABLE metadata (name text, value text)")
    db.execute("CREATE TABLE tiles (zoom_level integer, tile_column integer, "
               "tile_row integer, tile_data blob)")
    db.execute("CREATE UNIQUE INDEX tile_index on tiles "
               "(zoom_level, tile_column, tile_row)")
    for name, value in [
        ("name", "Bengaluru"),
        ("type", "baselayer"),
        ("version", "1.0"),
        ("description", "Offline Bengaluru basemap for Sankat-Mochan"),
        ("format", "png"),
        ("minzoom", str(args.minzoom)),
        ("maxzoom", str(args.maxzoom)),
        ("bounds", f"{MIN_LON},{MIN_LAT},{MAX_LON},{MAX_LAT}"),
        ("attribution", ATTRIBUTION),
    ]:
        db.execute("INSERT INTO metadata VALUES (?,?)", (name, value))

    total, ok, fail = 0, 0, 0
    for z in range(args.minzoom, args.maxzoom + 1):
        xs, ys = tile_ranges(z)
        for x in xs:
            for y in ys:
                total += 1
                url = TILE_URL.format(z=z, x=x, y=y)
                try:
                    data = fetch(url)
                except Exception as e:
                    fail += 1
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
        print(f"zoom {z}: {ok} tiles so far")

    db.commit()
    db.close()
    size = os.path.getsize(out)
    print(f"\nDone: {ok} tiles ({fail} missed of {total}) -> {out} ({size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
