"""High-level API: load datasets, run a similarity query, write results."""
from __future__ import annotations

import glob
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from . import raster as R
from .features import compute_features
from .similarity import (DEFAULT_WEIGHTS, common_features, query_vector, robust_scaler, search,
                         suitability, haversine_km)

ROOT = Path(__file__).resolve().parents[2]


class Catalog:
    def __init__(self, root=ROOT, scale_m=500.0, window_km=10.0):
        self.root = Path(root)
        self.scale_m, self.window_km = scale_m, window_km
        self.cfg = json.loads((self.root / "config/datasets.json").read_text())["datasets"]
        self.analogs = json.loads((self.root / "config/known_analogs.json").read_text())
        self.status, self.rasters, self.stacks = {}, {}, {}

    def _load(self, d):
        pats = d["path"] if isinstance(d["path"], list) else [d["path"]]
        paths = sorted(p for pat in pats for p in glob.glob(str(self.root / pat)))
        if not paths:
            return None
        if d["loader"] == "slope_image":
            return R.load_slope_image(paths[0], d["name"], d["body"])
        npz = [p for p in paths if p.endswith(".npz")]
        if npz:
            r = R.Raster.load_npz(npz[0]); r.name = d["name"]
            return r
        tifs = [p for p in paths if p.lower().endswith((".tif", ".tiff"))]
        if not tifs:
            raise ValueError(f"no readable file among {paths}")
        if len(tifs) == 1:
            return R.load_geotiff(tifs[0], d["name"], d["body"])
        return mosaic([R.load_geotiff(p, d["name"], d["body"]) for p in tifs])

    def load_all(self):
        for d in self.cfg:
            try:
                r = self._load(d)
            except Exception as e:                      # keep going if one dataset is broken
                self.status[d["name"]] = f"error: {e}"
                continue
            if r is None:
                self.status[d["name"]] = "missing"
                continue
            r.meta.update({k: d[k] for k in ("description", "synthetic") if k in d})
            self.rasters[d["name"]] = r
            self.status[d["name"]] = "ok"
        return self

    def stack(self, name):
        if name not in self.stacks:
            self.stacks[name] = compute_features(self.rasters[name], self.effective_scale_m(), self.window_km)
        return self.stacks[name]

    def effective_scale_m(self):
        """Common analysis scale: never finer than the coarsest loaded dataset."""
        return max([self.scale_m] + [r.pixel_m for r in self.rasters.values()])

    def find_dataset(self, lat, lon, body=None):
        for n, r in self.rasters.items():
            if (body is None or r.body == body) and r.contains(lat, lon):
                return n
        return None


def mosaic(parts):
    """Merge equirect tiles that share resolution into one raster."""
    dl, dn = parts[0].georef["dlat"], parts[0].georef["dlon"]
    top = max(p.georef["lat_top"] for p in parts)
    left = min(p.georef["lon_left"] for p in parts)
    bot = min(p.georef["lat_top"] - p.shape[0] * dl for p in parts)
    right = max(p.georef["lon_left"] + p.shape[1] * dn for p in parts)
    out = np.full((int(round((top - bot) / dl)), int(round((right - left) / dn))), np.nan, "float32")
    for p in parts:
        r0 = int(round((top - p.georef["lat_top"]) / dl))
        c0 = int(round((p.georef["lon_left"] - left) / dn))
        out[r0:r0 + p.shape[0], c0:c0 + p.shape[1]] = p.data
    g = dict(parts[0].georef, lat_top=top, lon_left=left)
    return R.Raster(parts[0].name, parts[0].body, parts[0].kind, out, g, parts[0].pixel_m, dict(parts[0].meta))


def run_query(cat: Catalog, lat, lon, qrad_km=25.0, pct=10.0, targets=None, top_n=10, weights=None,
              suit_weight=0.0, use_extras=False, min_area_km2=50.0):
    src = cat.find_dataset(lat, lon)
    if src is None:
        raise ValueError(f"({lat}, {lon}) is not covered by any loaded dataset: {list(cat.rasters)}")
    names_all = [src] + [n for n in (targets or cat.rasters) if n != src and n in cat.rasters]
    stacks = {n: cat.stack(n) for n in names_all}
    feats = common_features(list(stacks.values()), use_extras)
    med, iqr = robust_scaler(list(stacks.values()), feats)
    qv, npx = query_vector(stacks[src], lat, lon, qrad_km, feats)
    results = {}
    for n, st in stacks.items():
        sim, sites = search(st, qv, feats, med, iqr, weights, pct, min_area_km2, top_n, suit_weight)
        results[n] = {"stack": st, "sim": sim, "sites": sites, "suit": suitability(st)}
    return {"query": {"lat": lat, "lon": lon, "radius_km": qrad_km, "dataset": src, "cells": npx,
                      "features": dict(zip(feats, map(float, qv)))},
            "feature_names": feats, "results": results}


def sites_geojson(res):
    feats = []
    for n, r in res["results"].items():
        for i, s in enumerate(r["sites"], 1):
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [s.lon, s.lat]},
                          "properties": {"rank": i, **{k: v for k, v in asdict(s).items() if k not in ("lat", "lon")}}})
    return {"type": "FeatureCollection", "features": feats}
