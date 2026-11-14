"""Download MOLA MEGDR (PDS) tiles. Default: your original meg016 north tile. For 463 m/px (128 ppd) data use
meg128 and the matching megt??n???hb tiles - see docs/DATA.md."""
import argparse
from pathlib import Path
import requests

ap = argparse.ArgumentParser()
ap.add_argument("--dir", default="meg016")
ap.add_argument("--tile", default="megt90n000eb", help="tile basename")
ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "data/mars"))
a = ap.parse_args()
base = f"https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/{a.dir}/"
out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
for ext in ("img", "lbl"):
    fn = f"{a.tile}.{ext}"
    r = requests.get(base + fn, timeout=300)
    print(fn, r.status_code)
    if r.status_code == 200:
        (out / fn).write_bytes(r.content)
