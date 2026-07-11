#!/usr/bin/env python3
"""
Pack a directory of z/x/y.png raster tiles into a spec-compliant MBTiles SQLite file
for the mesh app's osmdroid OfflineTileProvider.

The tiles are pre-rendered from the command post's exact Protomaps "light" vector style
(see command-post/static/_render/) so the phone map matches the command post look —
same cream earth, pastel parks, blue water. XYZ input rows are converted to the MBTiles
TMS convention (tile_row = 2^z - 1 - y).

Usage:
    python pack_mbtiles.py <tiles_dir> <out.mbtiles>
"""
import glob
import io
import os
import sqlite3
import sys

from PIL import Image


def optimize_png(raw: bytes) -> bytes:
    """Quantize a 24-bit map tile to a 256-colour palette PNG. Map tiles use a small palette
    (earth, parks, water, roads, labels), so this shrinks each tile ~4x with no visible loss,
    keeping the bundled archive small — same size class as the previous CARTO tiles."""
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    pal = im.quantize(colors=256, method=Image.Quantize.FASTOCTREE)
    out = io.BytesIO()
    pal.save(out, format="PNG", optimize=True)
    packed = out.getvalue()
    return packed if len(packed) < len(raw) else raw  # never grow a tile

MINZOOM, MAXZOOM = 11, 15
BOUNDS = "77.45,12.83,77.75,13.14"
CENTER = "77.6,12.985,13"
ATTRIBUTION = "© OpenStreetMap contributors"  # Protomaps light / OSM data (ODbL)


def main(tiles_dir, out_path):
    if os.path.exists(out_path):
        os.remove(out_path)
    db = sqlite3.connect(out_path)
    db.execute("CREATE TABLE metadata (name TEXT, value TEXT)")
    db.execute("CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB)")
    db.execute("CREATE UNIQUE INDEX tile_index ON tiles (zoom_level, tile_column, tile_row)")
    meta = {
        "name": "Bengaluru",
        "type": "baselayer",
        "version": "1.2",
        "description": "Offline Bengaluru basemap for Sankat-Mochan (Protomaps light, matches command post)",
        "format": "png",
        "minzoom": str(MINZOOM),
        "maxzoom": str(MAXZOOM),
        "bounds": BOUNDS,
        "center": CENTER,
        "attribution": ATTRIBUTION,
    }
    db.executemany("INSERT INTO metadata VALUES (?,?)", list(meta.items()))

    n = 0
    for png in glob.glob(os.path.join(tiles_dir, "*", "*", "*.png")):
        parts = png.replace("\\", "/").split("/")
        z, x, y = int(parts[-3]), int(parts[-2]), int(parts[-1][:-4])
        tms_row = (2 ** z - 1) - y
        with open(png, "rb") as f:
            data = optimize_png(f.read())
        db.execute("INSERT OR REPLACE INTO tiles VALUES (?,?,?,?)", (z, x, tms_row, sqlite3.Binary(data)))
        n += 1
    db.commit()
    db.close()
    print(f"packed {n} tiles into {out_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
