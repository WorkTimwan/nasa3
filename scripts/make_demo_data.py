"""Write a SYNTHETIC Earth DEM so the pipeline can be exercised without downloads.
It is NOT real data and is flagged synthetic everywhere it is used."""
import sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
from analogfinder.raster import make_synthetic_dem
r = make_synthetic_dem()
out = root / "data/samples/demo_synthetic_earth.npz"
r.save_npz(out)
print("wrote", out)
