"""Download Copernicus GLO-90 DEM tiles for a bounding box (1x1 degree COG tiles, ~15 MB each).

  python scripts/download_earth.py --bbox -30 -15 -75 -60      # lat_s lat_n lon_w lon_e  (Andes)
  python scripts/download_earth.py --preset andes
Tiles are written to data/earth/. Needs internet access to copernicus-dem-90m.s3.eu-central-1.amazonaws.com
"""
import argparse
import math
from pathlib import Path

import requests

PRESETS = {"andes": (-30, -15, -75, -60), "atacama": (-26, -22, -71, -67), "death_valley": (35, 37, -118, -116),
           "iceland": (63, 66, -20, -14), "devon_island": (75, 76, -92, -86)}
BASE = "https://copernicus-dem-90m.s3.eu-central-1.amazonaws.com"


def tile_name(lat, lon):
    ns, ew = ("N" if lat >= 0 else "S"), ("E" if lon >= 0 else "W")
    return f"Copernicus_DSM_COG_30_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbox", type=float, nargs=4, metavar=("LAT_S", "LAT_N", "LON_W", "LON_E"))
    ap.add_argument("--preset", choices=PRESETS)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "data/earth"))
    a = ap.parse_args()
    s, n, w, e = PRESETS[a.preset] if a.preset else a.bbox
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    for lat in range(math.floor(s), math.ceil(n)):
        for lon in range(math.floor(w), math.ceil(e)):
            nm = tile_name(lat, lon)
            dst = out / f"{nm}.tif"
            if dst.exists():
                continue
            r = requests.get(f"{BASE}/{nm}/{nm}.tif", stream=True, timeout=120)
            if r.status_code != 200:
                print(f"skip {nm} (HTTP {r.status_code}; ocean tiles do not exist)")
                continue
            with open(dst, "wb") as f:
                for ch in r.iter_content(1 << 20):
                    f.write(ch)
            print("saved", dst)


if __name__ == "__main__":
    main()
