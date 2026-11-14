"""Flask backend + static frontend.   python -m analogfinder.server"""
import base64
from dataclasses import asdict
from pathlib import Path

import numpy as np
from flask import Flask, jsonify, request, send_from_directory

from .pipeline import ROOT, Catalog, run_query, sites_geojson
from .render import base_png, overlay_png

app = Flask(__name__, static_folder=None)
CAT = None
b64 = lambda b: "data:image/png;base64," + base64.b64encode(b).decode()


def cat():
    global CAT
    if CAT is None:
        CAT = Catalog().load_all()
    return CAT


def px(stack, lat, lon):
    r, c = stack.raster.latlon_to_rc(lat, lon)
    f = stack.scale_m / stack.raster.pixel_m
    return float((c + 0.5) / f - 0.5), float((r + 0.5) / f - 0.5)


@app.get("/")
def index():
    return send_from_directory(ROOT / "frontend", "index.html")


@app.get("/api/status")
def status():
    c = cat()
    out = []
    for d in c.cfg:
        r = c.rasters.get(d["name"])
        out.append({"name": d["name"], "body": d["body"], "status": c.status[d["name"]],
                    "description": d["description"], "synthetic": bool(d.get("synthetic")),
                    "shape": list(r.shape) if r else None, "pixel_m": r.pixel_m if r else None})
    return jsonify({"datasets": out, "analogs": c.analogs["sites"], "scale_m": c.effective_scale_m() if c.rasters else None})


@app.get("/api/base/<name>")
def base(name):
    c = cat()
    if name not in c.rasters:
        return jsonify(error="unknown dataset"), 404
    st = c.stack(name)
    return jsonify({"image": b64(base_png(st)), "w": st.cube.shape[1], "h": st.cube.shape[0]})


@app.get("/api/ll")
def ll():
    st = cat().stack(request.args["dataset"])
    x, y = float(request.args["x"]), float(request.args["y"])
    f = st.scale_m / st.raster.pixel_m
    lat, lon = st.raster.rc_to_latlon((y + 0.5) * f - 0.5, (x + 0.5) * f - 0.5)
    return jsonify(lat=float(lat), lon=float(lon))


@app.post("/api/query")
def query():
    j = request.get_json(force=True)
    c = cat()
    try:
        res = run_query(c, float(j["lat"]), float(j["lon"]), float(j.get("radius_km", 25)), float(j.get("pct", 10)),
                        top_n=int(j.get("top_n", 10)), suit_weight=float(j.get("suit_weight", 0)),
                        use_extras=bool(j.get("use_extras", False)), weights=j.get("weights"))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    out = {"query": res["query"], "features": res["feature_names"], "datasets": {}}
    for n, r in res["results"].items():
        st = r["stack"]
        sites = []
        for i, s in enumerate(r["sites"], 1):
            x, y = px(st, s.lat, s.lon)
            sites.append({"rank": i, **asdict(s), "x": x, "y": y})
        out["datasets"][n] = {"body": st.body, "overlay": b64(overlay_png(r["sim"], 0.2)),
                              "suit": b64(overlay_png(r["suit"], 0.0, "viridis")), "sites": sites,
                              "synthetic": bool(st.raster.meta.get("synthetic"))}
    qx, qy = px(res["results"][res["query"]["dataset"]]["stack"], res["query"]["lat"], res["query"]["lon"])
    out["query"].update(x=qx, y=qy)
    return jsonify(out)


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1")
    a = p.parse_args()
    cat()
    print(f"Open http://{a.host}:{a.port}")
    app.run(host=a.host, port=a.port, debug=False)


if __name__ == "__main__":
    main()
