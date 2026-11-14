"""Scale-aware terrain feature extraction.

Every raster is first reduced to a common analysis scale (``scale_m`` metres per cell)
so that Earth 90 m DEMs, Moon 500 m slope maps and Mars MOLA grids are compared at the
same ground sampling. Features are then computed in a moving window of ``window_km``.

Universal features (work for DEMs *and* slope-only maps):
    slope_mean   mean slope (deg)
    slope_std    slope variability  -> roughness
    flat_frac    fraction of cells with slope < 5 deg   (landing / construction friendly)
    steep_frac   fraction of cells with slope > 15 deg  (scarps, crater walls, canyon walls)
    coherence    structure-tensor coherence of the slope field (0 isotropic .. 1 lineated)
                 -> proxy for tectonic fabric / lineaments / aligned ridges
    edge_density fraction of cells on strong slope edges (fault scarps, crater rims)
DEM-only extras:
    relief_m     local max-min elevation (m)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage as ndi

from .raster import Raster

UNIVERSAL = ["slope_mean", "slope_std", "flat_frac", "steep_frac", "coherence", "edge_density"]
EXTRA_DEM = ["relief_m"]


@dataclass
class FeatureStack:
    name: str
    body: str
    names: list
    cube: np.ndarray          # (H, W, F) float32, NaN where invalid
    rows: np.ndarray          # coarse-row -> full-res row (centre)
    cols: np.ndarray
    scale_m: float
    window: int
    raster: Raster

    def latlon(self):
        rr, cc = np.meshgrid(self.rows, self.cols, indexing="ij")
        return self.raster.rc_to_latlon(rr, cc)

    def cell_area_km2(self):
        lat, _ = self.latlon()
        g = self.raster.georef["type"]
        a = (self.scale_m / 1000.0) ** 2
        if g == "equirect":
            return a * np.ones_like(lat)
        return a * np.ones_like(lat)


def _block_reduce(arr, f):
    if f <= 1:
        return arr
    h, w = (arr.shape[0] // f) * f, (arr.shape[1] // f) * f
    a = arr[:h, :w].reshape(h // f, f, w // f, f)
    valid = np.isfinite(a)
    cnt = valid.sum((1, 3))
    s = np.where(valid, a, 0).sum((1, 3))
    out = np.where(cnt >= (f * f) / 2, s / np.maximum(cnt, 1), np.nan)
    return out.astype("float32")


def _fill(a):
    """Replace NaN by nearest valid for filters; returns filled array and mask."""
    m = np.isfinite(a)
    if m.all():
        return a, m
    if not m.any():
        return np.zeros_like(a), m
    idx = ndi.distance_transform_edt(~m, return_distances=False, return_indices=True)
    return a[tuple(idx)], m


def _slope_from_dem(dem, r: Raster, f, rows):
    dy, dx = r.pixel_size_m_at(rows)
    dy = dy * f
    dx = (dx * f)[:, None]
    filled, m = _fill(dem)
    gy = np.gradient(filled, axis=0) / np.mean(dy)
    gx = np.gradient(filled, axis=1) / dx
    s = np.degrees(np.arctan(np.hypot(gx, gy))).astype("float32")
    s[~m] = np.nan
    return s


def _mean_filter(a, w):
    return ndi.uniform_filter(a, w, mode="nearest")


def compute_features(r: Raster, scale_m=500.0, window_km=10.0, max_cells=1800) -> FeatureStack:
    f = max(1, int(round(scale_m / r.pixel_m)))
    # cap the working grid size
    while max(r.shape) // f > max_cells:
        f += 1
    scale = r.pixel_m * f
    data = _block_reduce(r.data, f)
    rows = (np.arange(data.shape[0]) + 0.5) * f - 0.5
    cols = (np.arange(data.shape[1]) + 0.5) * f - 0.5

    if r.kind == "dem":
        slope = _slope_from_dem(data, r, f, rows)
    else:
        slope = data.copy()
    valid = np.isfinite(slope)
    s, _ = _fill(slope)

    win = max(5, int(round(window_km * 1000 / scale)) | 1)
    m1 = _mean_filter(s, win)
    var = np.maximum(_mean_filter(s * s, win) - m1 * m1, 0)
    flat = _mean_filter((s < 5).astype("float32"), win)
    steep = _mean_filter((s > 15).astype("float32"), win)

    # structure tensor of the slope field -> directional coherence
    sg = ndi.gaussian_filter(s, 1.0)
    gy, gx = np.gradient(sg)
    jxx, jyy, jxy = (_mean_filter(gx * gx, win), _mean_filter(gy * gy, win), _mean_filter(gx * gy, win))
    tr = jxx + jyy
    disc = np.sqrt(np.maximum((jxx - jyy) ** 2 + 4 * jxy ** 2, 0))
    coh = np.where(tr > 1e-6, disc / np.maximum(tr, 1e-6), 0)
    gm = np.hypot(gx, gy)
    edge = _mean_filter((gm > np.nanpercentile(gm[valid], 85)).astype("float32"), win) if valid.any() else gm * 0

    layers = {"slope_mean": m1, "slope_std": np.sqrt(var), "flat_frac": flat, "steep_frac": steep,
              "coherence": coh, "edge_density": edge}
    if r.kind == "dem":
        filled, _ = _fill(data)
        layers["relief_m"] = ndi.maximum_filter(filled, win) - ndi.minimum_filter(filled, win)

    names = list(layers)
    cube = np.stack([layers[n] for n in names], -1).astype("float32")
    # drop the window border (filters unreliable) and invalid cells
    cube[~valid] = np.nan
    b = win // 2
    cube[:b] = np.nan
    cube[-b:] = np.nan
    cube[:, :b] = np.nan
    cube[:, -b:] = np.nan
    return FeatureStack(r.name, r.body, names, cube, rows, cols, scale, win, r)
