"""Command line:  python -m analogfinder query --lat -22.5 --lon -67.5 --radius 25 --pct 10 --out outputs/andes"""
import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .pipeline import Catalog, run_query, sites_geojson


def cmd_status(a):
    c = Catalog().load_all()
    for n, s in c.status.items():
        print(f"{n:28s} {s}")


def cmd_query(a):
    c = Catalog(scale_m=a.scale, window_km=a.window).load_all()
    res = run_query(c, a.lat, a.lon, a.radius, a.pct, top_n=a.top, suit_weight=a.suit_weight, use_extras=a.extras)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    q = res["query"]
    print(f"Query in {q['dataset']} ({q['cells']} cells) features: " + ", ".join(f"{k}={v:.2f}" for k, v in q["features"].items()))
    rows = []
    for n, r in res["results"].items():
        st, sim = r["stack"], r["sim"]
        fig, ax = plt.subplots(1, 2, figsize=(14, 7))
        s = st.cube[..., st.names.index("slope_mean")]
        ax[0].imshow(s, cmap="gray_r", vmin=0, vmax=20)
        im = ax[0].imshow(np.where(sim >= np.nanpercentile(sim, 100 - a.pct), sim, np.nan), cmap="autumn_r", vmin=0, vmax=1, alpha=.75)
        ax[1].imshow(r["suit"], cmap="viridis", vmin=0, vmax=1)
        for i, site in enumerate(r["sites"], 1):
            rr, cc = st.raster.latlon_to_rc(site.lat, site.lon)
            f = st.scale_m / st.raster.pixel_m
            ax[0].annotate(str(i), ((cc + .5) / f - .5, (rr + .5) / f - .5), color="cyan", weight="bold", ha="center")
            rows.append({"dataset": n, "body": st.body, "rank": i, **{k: v for k, v in asdict(site).items() if k != "features"}})
        ax[0].set_title(f"{n}: similarity to query ({a.pct}% best)"); ax[1].set_title("Station suitability (flat, smooth)")
        for x in ax: x.axis("off")
        if st.raster.meta.get("synthetic"):
            fig.suptitle("SYNTHETIC DEMO DATA - not real terrain", color="red")
        fig.colorbar(im, ax=ax[0], fraction=.04, label="similarity")
        fig.savefig(out / f"map_{n}.png", dpi=110, bbox_inches="tight"); plt.close(fig)
    with open(out / "candidate_sites.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])) if rows else None
        if w:
            w.writeheader(); w.writerows(rows)
    (out / "candidate_sites.geojson").write_text(json.dumps(sites_geojson(res)))
    print(f"{len(rows)} candidate sites -> {out}/")


def main():
    p = argparse.ArgumentParser(prog="analogfinder")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(f=cmd_status)
    q = sub.add_parser("query")
    q.add_argument("--lat", type=float, required=True); q.add_argument("--lon", type=float, required=True)
    q.add_argument("--radius", type=float, default=25, help="query radius km")
    q.add_argument("--pct", type=float, default=10); q.add_argument("--top", type=int, default=10)
    q.add_argument("--scale", type=float, default=500, help="analysis scale m/cell")
    q.add_argument("--window", type=float, default=10, help="feature window km")
    q.add_argument("--suit-weight", type=float, default=0.0); q.add_argument("--extras", action="store_true")
    q.add_argument("--out", default="outputs/query")
    q.set_defaults(f=cmd_query)
    a = p.parse_args(); a.f(a)
