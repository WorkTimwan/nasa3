#!/usr/bin/env python3
"""One command to fetch REAL open data for Earth, Mars and Moon and convert it for analogfinder.

    python scripts/fetch_all_data.py                      # everything, default Andes + global Mars/Moon
    python scripts/fetch_all_data.py --only earth --preset atacama
    python scripts/fetch_all_data.py --mars-res 64        # finer MOLA (pixels per degree: 16/32/64/128)

Sources (all open, no login):
  Earth  Copernicus GLO-90 DEM        AWS open data  (tiles around the preset/bbox)
  Mars   MOLA MEGDR                   NASA PDS Geosciences Node
  Moon   LOLA LDEM (cylindrical)      NASA PDS Geosciences Node
Needs: pip install requests numpy pillow   (rasterio optional)
Each step reports failures and carries on; nothing is invented if a download fails.
"""
import argparse, re, sys
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

PDS = "https://pds-geosciences.wustl.edu"
MARS_BASE = PDS + "/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/"
MOON_BASE = PDS + "/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/cylindrical/img/"


def get(url, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=180) as r:
        r.raise_for_status()
        done = 0
        with open(dst, "wb") as f:
            for ch in r.iter_content(1 << 20):
                f.write(ch); done += len(ch)
                print(f"\r  {dst.name}: {done/1e6:.0f} MB", end="", flush=True)
    print()


def listing(url, pattern):
    html = requests.get(url, timeout=60).text
    return sorted(set(re.findall(pattern, html, re.I)))


def earth(a):
    import download_earth
    print("== Earth: Copernicus GLO-90")
    bbox = download_earth.PRESETS[a.preset]
    sys.argv = ["download_earth", "--bbox", *map(str, bbox)]
    download_earth.main()


def pds_dem(base, name_filter, out_name, body, ppd, a):
    from analogfinder.raster import load_pds_img
    files = listing(base, r'href="([^"]+\.(?:img|lbl))"')
    files = [f.split("/")[-1] for f in files]
    print("  available:", ", ".join(files[:12]), "…" if len(files) > 12 else "")
    stem = next((f[:-4] for f in files if f.lower().endswith(".img") and name_filter(f)), None)
    if not stem:
        raise RuntimeError(f"no matching file at {base} (check docs/DATA.md)")
    raw = ROOT / "data" / body
    for ext in ("IMG", "LBL"):
        fn = next(f for f in files if f.lower() == f"{stem.lower()}.{ext.lower()}")
        get(base + fn, raw / fn)
    r = load_pds_img(raw / f"{stem}.IMG" if (raw / f"{stem}.IMG").exists() else raw / f"{stem}.img",
                     raw / f"{stem}.LBL" if (raw / f"{stem}.LBL").exists() else raw / f"{stem}.lbl",
                     out_name, body)
    out = ROOT / "data/samples" / f"{out_name}.npz"
    r.save_npz(out)
    print(f"  saved {out}  shape={r.shape}  pixel={r.pixel_m:.0f} m")


def mars(a):
    print("== Mars: MOLA MEGDR")
    # global-ish mosaics are named megtNNNeNNN; fall back to your known polar-north tile for 16 ppd
    d = f"meg{a.mars_res:03d}"
    pds_dem(MARS_BASE + d + "/", lambda f: f.lower().startswith("megt") or f.lower().startswith("megr"),
            "mars_mola", "mars", a.mars_res, a)


def moon(a):
    print("== Moon: LOLA LDEM")
    pds_dem(MOON_BASE, lambda f: f.upper().startswith(f"LDEM_{a.moon_res}."), "moon_lola_ldem", "moon", a.moon_res, a)


if __name__ == "__main__":
    import download_earth
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["earth", "mars", "moon"])
    ap.add_argument("--preset", default="andes", choices=list(download_earth.PRESETS))
    ap.add_argument("--mars-res", type=int, default=32, choices=[16, 32, 64, 128])
    ap.add_argument("--moon-res", type=int, default=16, choices=[4, 16, 64, 128])
    a = ap.parse_args()
    for name, fn in (("earth", earth), ("mars", mars), ("moon", moon)):
        if a.only in (None, name):
            try:
                fn(a)
            except Exception as e:
                print(f"  !! {name} failed: {e}\n     See docs/DATA.md for a manual download.")
    print("\nDone. Start the app:  cd backend && python -m analogfinder.server")
