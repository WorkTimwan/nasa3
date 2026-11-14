"""Convert a Mars/Moon Trek STL export to .npz. Trek STLs are normalised meshes with NO coordinates:
you must supply the lat/lon box you exported and (optionally) the vertical scale in metres.

  python scripts/import_trek_stl.py trek.stl --body mars --bbox -10 10 120 140 --z-scale 500
"""
import argparse, sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
from analogfinder.raster import load_stl_heightfield

ap = argparse.ArgumentParser()
ap.add_argument("stl"); ap.add_argument("--body", default="mars"); ap.add_argument("--name", default="mars_trek")
ap.add_argument("--bbox", type=float, nargs=4, metavar=("LAT_S", "LAT_N", "LON_W", "LON_E"), required=True)
ap.add_argument("--z-scale", type=float, default=1.0)
ap.add_argument("--out")
a = ap.parse_args()
r = load_stl_heightfield(a.stl, a.name, a.body, tuple(a.bbox), a.z_scale)
out = a.out or str(root / f"data/samples/{a.name}.npz")
r.save_npz(out)
print("saved", out, r.shape)
