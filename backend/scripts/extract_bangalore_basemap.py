"""One-shot: extract a Bangalore-area vector basemap from the remote Protomaps v4
daily build into a local PMTiles archive (offline demo tiles).

Reads the huge remote build (build.protomaps.com/<date>.pmtiles) over HTTP range
requests — only the header, directories, and the ~2k tiles inside the Bangalore
bounding box are fetched, never the whole planet. Output tiles stay GZIP-compressed
(matching the /vtiles Content-Encoding: gzip the FastAPI server sets).

Adapted from the documented pmtiles Python reader/writer API
(https://github.com/protomaps/PMTiles, BSD-3). Run from backend/ with the venv.
"""
import io
import math
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
from pmtiles.reader import Reader
from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import Writer

SRC = "https://build.protomaps.com/20260711.pmtiles"
OUT = "static/bangalore.pmtiles"

# Bengaluru city box (~0.40° x 0.35°, similar footprint to the old Wayanad extract).
MIN_LON, MAX_LON = 77.40, 77.80
MIN_LAT, MAX_LAT = 12.80, 13.15
MINZOOM, MAXZOOM = 0, 15
CENTER_LON, CENTER_LAT, CENTER_Z = 77.5946, 12.9716, 12

_client = httpx.Client(timeout=30.0, follow_redirects=True)
_cache = {}
_lock = threading.Lock()


def get_bytes(offset, length):
    key = (offset, length)
    with _lock:
        if key in _cache:
            return _cache[key]
    hdrs = {"Range": f"bytes={offset}-{offset + length - 1}"}
    for attempt in range(4):
        try:
            r = _client.get(SRC, headers=hdrs)
            r.raise_for_status()
            data = r.content
            # cache only small directory/header reads, not big tile payloads
            if length <= 32768:
                with _lock:
                    _cache[key] = data
            return data
        except Exception as e:  # noqa: BLE001 — retry transient range failures
            if attempt == 3:
                raise
    raise RuntimeError("unreachable")


def lonlat_to_tile(lon, lat, z):
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n)
    return max(0, min(n - 1, x)), max(0, min(n - 1, y))


def target_tiles():
    for z in range(MINZOOM, MAXZOOM + 1):
        x0, y0 = lonlat_to_tile(MIN_LON, MAX_LAT, z)  # NW
        x1, y1 = lonlat_to_tile(MAX_LON, MIN_LAT, z)  # SE
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                yield z, x, y


def main():
    reader = Reader(get_bytes)
    src_header = reader.header()
    src_meta = reader.metadata()
    print(f"source build: {SRC}")
    print(f"source zoom {src_header['min_zoom']}..{src_header['max_zoom']}, "
          f"tile_type={src_header['tile_type']}, compression={src_header['tile_compression']}")

    tiles = list(target_tiles())
    print(f"bbox tiles to probe (z{MINZOOM}-{MAXZOOM}): {len(tiles)}")

    results = {}
    done = [0]

    def fetch(zxy):
        z, x, y = zxy
        try:
            data = reader.get(z, x, y)
        except Exception:
            data = None
        with _lock:
            done[0] += 1
            if done[0] % 250 == 0:
                print(f"  probed {done[0]}/{len(tiles)}, kept {len(results)}")
        if data:
            results[zxy] = data

    with ThreadPoolExecutor(max_workers=16) as ex:
        list(ex.map(fetch, tiles))

    print(f"non-empty tiles: {len(results)}")
    if not results:
        print("ERROR: no tiles found in bbox — aborting", file=sys.stderr)
        sys.exit(1)

    with open(OUT, "wb") as f:
        writer = Writer(f)
        for zxy in sorted(results, key=lambda t: zxy_to_tileid(*t)):
            writer.write_tile(zxy_to_tileid(*zxy), results[zxy])
        header = {
            "version": 3,
            "tile_type": TileType.MVT,
            "tile_compression": Compression.GZIP,
            "internal_compression": Compression.GZIP,
            "min_zoom": MINZOOM,
            "max_zoom": MAXZOOM,
            "min_lon_e7": int(MIN_LON * 1e7),
            "min_lat_e7": int(MIN_LAT * 1e7),
            "max_lon_e7": int(MAX_LON * 1e7),
            "max_lat_e7": int(MAX_LAT * 1e7),
            "center_zoom": CENTER_Z,
            "center_lon_e7": int(CENTER_LON * 1e7),
            "center_lat_e7": int(CENTER_LAT * 1e7),
        }
        writer.finalize(header, src_meta)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
