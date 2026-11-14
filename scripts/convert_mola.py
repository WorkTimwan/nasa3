"""PDS3 .IMG/.LBL -> GeoTIFF-free .npz that the project reads directly (no rasterio needed)."""
import argparse, sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
from analogfinder.raster import load_pds_img

ap = argparse.ArgumentParser()
ap.add_argument("img"); ap.add_argument("lbl"); ap.add_argument("--name", default="mars_mola")
ap.add_argument("--out", default=str(root / "data/samples/mars_mola.npz"))
a = ap.parse_args()
r = load_pds_img(a.img, a.lbl, a.name)
r.save_npz(a.out)
print("saved", a.out, r.shape, r.georef)
