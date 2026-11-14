"""Similarity search, candidate-site extraction and station-suitability scoring."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage as ndi

from .features import FeatureStack

DEFAULT_WEIGHTS = {"slope_mean": 1.0, "slope_std": 1.0, "flat_frac": 1.0, "steep_frac": 0.7,
                   "coherence": 0.8, "edge_density": 0.7, "relief_m": 0.8}


def haversine_km(lat1, lon1, lat2, lon2, radius_km):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians(lon2 - lon1)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * radius_km * np.arcsin(np.sqrt(a))


def common_features(stacks, use_extras=True):
    names = set(stacks[0].names)
    for s in stacks[1:]:
        names &= set(s.names)
    order = [n for n in stacks[0].names if n in names]
    if not use_extras:
        order = [n for n in order if n != "relief_m"]
    return order


def robust_scaler(stacks, names):
    """Pooled median / IQR over all datasets so features are comparable across bodies."""
    cols = []
    for s in stacks:
        idx = [s.names.index(n) for n in names]
        cols.append(s.cube[..., idx].reshape(-1, len(names)))
    X = np.concatenate(cols)
    X = X[np.isfinite(X).all(1)]
    med = np.median(X, 0)
    iqr = np.percentile(X, 75, 0) - np.percentile(X, 25, 0)
    return med, np.where(iqr > 1e-9, iqr, 1.0)


def query_vector(stack: FeatureStack, lat, lon, radius_km, names):
    r, c = stack.raster.latlon_to_rc(lat, lon)
    lat_g, lon_g = stack.latlon()
    d = haversine_km(lat, lon, lat_g, lon_g, stack.raster.radius_km)
    m = d <= max(radius_km, stack.scale_m / 1000 * 1.5)
    idx = [stack.names.index(n) for n in names]
    X = stack.cube[..., idx][m]
    X = X[np.isfinite(X).all(1)]
    if len(X) == 0:
        raise ValueError("query location has no valid data in this dataset")
    return X.mean(0), int(len(X))


def suitability(stack: FeatureStack):
    """0..1 'buildability' for a surface station: flat, smooth, few scarps, low relief."""
    g = lambda n: stack.cube[..., stack.names.index(n)]
    s = 1 - np.clip(g("slope_mean") / 12.0, 0, 1)
    f = g("flat_frac")
    st = 1 - np.clip(g("steep_frac") / 0.25, 0, 1)
    rg = 1 - np.clip(g("slope_std") / 8.0, 0, 1)
    return (0.3 * s + 0.3 * f + 0.2 * st + 0.2 * rg).astype("float32")


@dataclass
class Site:
    dataset: str
    body: str
    lat: float
    lon: float
    area_km2: float
    similarity: float
    suitability: float
    score: float
    features: dict


def search(stack: FeatureStack, qvec, names, med, iqr, weights=None, pct=10.0, min_area_km2=50.0,
           top_n=10, suit_weight=0.0):
    """Return (similarity map 0..1, list[Site])."""
    w = np.array([(weights or DEFAULT_WEIGHTS).get(n, 1.0) for n in names], float)
    idx = [stack.names.index(n) for n in names]
    Z = (stack.cube[..., idx] - med) / iqr
    q = (qvec - med) / iqr
    D = np.sqrt(((Z - q) ** 2 * w).sum(-1) / w.sum())
    valid = np.isfinite(D)
    sim = np.full(D.shape, np.nan, "float32")
    sim[valid] = np.exp(-(D[valid] ** 2) / 2.0)             # 1 = identical, ~0.6 = 1 IQR away
    suit = suitability(stack)
    thr = np.nanpercentile(sim, 100 - pct) if valid.any() else 1.0
    mask = valid & (sim >= thr)
    lab, n = ndi.label(mask)
    lat, lon = stack.latlon()
    ca = stack.scale_m ** 2 / 1e6
    sites = []
    for i in range(1, n + 1):
        m = lab == i
        area = float(m.sum() * ca)
        if area < min_area_km2:
            continue
        wts = sim[m]
        # centroid on the sphere via unit vectors
        la, lo = np.radians(lat[m]), np.radians(lon[m])
        v = np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], -1)
        c = (v * wts[:, None]).sum(0)
        c /= np.linalg.norm(c) + 1e-12
        clat, clon = np.degrees(np.arcsin(c[2])), np.degrees(np.arctan2(c[1], c[0]))
        ms, mf = float(np.nanmean(sim[m])), float(np.nanmean(suit[m]))
        score = (1 - suit_weight) * ms + suit_weight * mf
        sites.append(Site(stack.name, stack.body, float(clat), float(clon), area, ms, mf,
                          float(score * (1 + 0.1 * np.log10(max(area, 1)))),
                          {n: float(np.nanmean(stack.cube[..., stack.names.index(n)][m])) for n in stack.names}))
    sites.sort(key=lambda s: -s.score)
    return sim, sites[:top_n]
