"""Raster container with geo-referencing and loaders for the data we support.

Supported sources
-----------------
* GeoTIFF DEM (Copernicus GLO-90, MOLA, LOLA ...)  -> rasterio if installed,
  otherwise a Pillow fallback that reads the GeoTIFF tags directly.
* PDS3 .IMG + .LBL (MOLA MEGDR)                    -> pure numpy reader.
* Colour-coded slope image with a colour bar       -> LUT decoder (LOLA polar map).
* Binary STL height-field (Mars Trek export)       -> grid reconstruction.
* .npz produced by this project.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import BODY_RADIUS_KM


@dataclass
class Raster:
    name: str
    body: str
    kind: str                      # "dem" (metres) or "slope" (degrees)
    data: np.ndarray               # 2-D float32, NaN = no data
    georef: dict                   # see below
    pixel_m: float                 # nominal ground size of one pixel (metres)
    meta: dict = field(default_factory=dict)

    # georef schemes
    #  {"type":"equirect","lat_top":..,"lon_left":..,"dlat":..,"dlon":..}
    #  {"type":"polar_south","cx":..,"cy":..,"r_px":..,"colat_edge":..,"lon_offset":0}
    #  {"type":"none"}  (uncalibrated; pixel coordinates only)

    @property
    def shape(self):
        return self.data.shape

    @property
    def radius_km(self):
        return BODY_RADIUS_KM[self.body]

    # ---- pixel <-> lat/lon -------------------------------------------------
    def rc_to_latlon(self, r, c):
        r = np.asarray(r, float)
        c = np.asarray(c, float)
        g = self.georef
        if g["type"] == "equirect":
            lat = g["lat_top"] - (r + 0.5) * g["dlat"]
            lon = g["lon_left"] + (c + 0.5) * g["dlon"]
            return lat, ((lon + 180) % 360) - 180
        if g["type"] == "polar_south":
            dx, dy = c - g["cx"], r - g["cy"]
            rho = np.hypot(dx, dy)
            k = np.tan(np.radians(g["colat_edge"]) / 2) / g["r_px"]
            colat = 2 * np.degrees(np.arctan(k * rho))
            lon = np.degrees(np.arctan2(dx, -dy)) + g.get("lon_offset", 0.0)
            return -90 + colat, ((lon + 180) % 360) - 180
        return np.full_like(r, np.nan), np.full_like(c, np.nan)

    def latlon_to_rc(self, lat, lon):
        g = self.georef
        lat = float(lat)
        lon = float(lon)
        if g["type"] == "equirect":
            dl = ((lon - g["lon_left"]) % 360)
            c = dl / g["dlon"] - 0.5
            r = (g["lat_top"] - lat) / g["dlat"] - 0.5
            return r, c
        if g["type"] == "polar_south":
            colat = lat + 90
            k = np.tan(np.radians(g["colat_edge"]) / 2) / g["r_px"]
            rho = np.tan(np.radians(colat) / 2) / k
            th = np.radians(lon - g.get("lon_offset", 0.0))
            return g["cy"] - rho * np.cos(th), g["cx"] + rho * np.sin(th)
        raise ValueError("raster is not geo-referenced")

    def contains(self, lat, lon):
        try:
            r, c = self.latlon_to_rc(lat, lon)
        except ValueError:
            return False
        h, w = self.shape
        if not (0 <= r < h and 0 <= c < w):
            return False
        return bool(np.isfinite(self.data[int(round(r)), int(round(c))]))

    def pixel_size_m_at(self, r):
        """(dy, dx) ground size in metres for row r (array-friendly)."""
        g = self.georef
        if g["type"] == "equirect":
            dy = np.radians(g["dlat"]) * self.radius_km * 1000
            lat, _ = self.rc_to_latlon(np.asarray(r), 0)
            dx = np.radians(g["dlon"]) * self.radius_km * 1000 * np.maximum(np.cos(np.radians(lat)), 0.05)
            return dy + 0 * dx, dx
        return np.full_like(np.asarray(r, float), self.pixel_m), np.full_like(np.asarray(r, float), self.pixel_m)

    # ---- persistence -------------------------------------------------------
    def save_npz(self, path):
        np.savez_compressed(path, data=self.data, name=self.name, body=self.body, kind=self.kind,
                            pixel_m=self.pixel_m, georef=json.dumps(self.georef), meta=json.dumps(self.meta))

    @staticmethod
    def load_npz(path):
        z = np.load(path, allow_pickle=False)
        return Raster(str(z["name"]), str(z["body"]), str(z["kind"]), z["data"].astype("float32"),
                      json.loads(str(z["georef"])), float(z["pixel_m"]), json.loads(str(z["meta"])))


# --------------------------------------------------------------------------
# GeoTIFF
# --------------------------------------------------------------------------
def load_geotiff(path, name, body, kind="dem", nodata=None):
    path = str(path)
    try:
        import rasterio
        with rasterio.open(path) as ds:
            arr = ds.read(1, masked=True).astype("float32").filled(np.nan)
            t = ds.transform
            dlon, dlat = t.a, -t.e
            lon_left, lat_top = t.c, t.f
    except ImportError:
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None
        im = Image.open(path)
        tags = im.tag_v2
        scale = tags.get(33550)
        tie = tags.get(33922)
        if scale is None or tie is None:
            raise RuntimeError("GeoTIFF tags missing; install rasterio (pip install rasterio)")
        arr = np.array(im, dtype="float32")
        dlon, dlat = scale[0], scale[1]
        lon_left, lat_top = tie[3], tie[4]
        nd = tags.get(42113)
        if nd is not None:
            try:
                arr[arr == float(str(nd).strip("\x00"))] = np.nan
            except ValueError:
                pass
    if nodata is not None:
        arr[arr == nodata] = np.nan
    R = BODY_RADIUS_KM[body] * 1000
    return Raster(name, body, kind, arr,
                  {"type": "equirect", "lat_top": lat_top, "lon_left": lon_left, "dlat": dlat, "dlon": dlon},
                  float(np.radians(dlat) * R), {"source": path})


# --------------------------------------------------------------------------
# PDS3 IMG/LBL (MOLA MEGDR)
# --------------------------------------------------------------------------
def _pds_label(lbl_path):
    txt = Path(lbl_path).read_text(errors="ignore")
    out = {}
    for m in re.finditer(r"^\s*([A-Z_^:]+)\s*=\s*(.+?)\s*$", txt, re.M):
        out[m.group(1)] = m.group(2).strip().strip('"')
    return out


def _num(s):
    return float(re.match(r"[-+0-9.eE]+", s).group(0))


def load_pds_img(img_path, lbl_path, name, body="mars", kind="dem", max_cells=None):
    """PDS3 equirectangular DEM (MOLA MEGDR, LOLA LDEM). Handles MSB/LSB byte order.

    Missing latitude/longitude keys fall back to a global 90N..-90 / 0E..360E grid.
    """
    L = _pds_label(lbl_path)
    lines, samples = int(L["LINES"]), int(L["LINE_SAMPLES"])
    bits = int(L.get("SAMPLE_BITS", 16))
    little = "LSB" in L.get("SAMPLE_TYPE", "MSB").upper() or "PC_" in L.get("SAMPLE_TYPE", "").upper()
    dtype = ("<" if little else ">") + {16: "i2", 32: "f4"}[bits]
    arr = np.fromfile(img_path, dtype=dtype, count=lines * samples).reshape(lines, samples).astype("float32")
    arr = arr * _num(L.get("SCALING_FACTOR", "1")) + _num(L.get("OFFSET", "0"))
    ppd = _num(L["MAP_RESOLUTION"]) if "MAP_RESOLUTION" in L else samples / 360.0
    lat_top = _num(L["MAXIMUM_LATITUDE"]) if "MAXIMUM_LATITUDE" in L else 90.0
    lon_left = _num(L["WESTERNMOST_LONGITUDE"]) if "WESTERNMOST_LONGITUDE" in L else 0.0
    for key in ("MISSING_CONSTANT", "MISSING"):
        if key in L:
            arr[arr == _num(L[key])] = np.nan
    R = BODY_RADIUS_KM[body] * 1000
    return Raster(name, body, kind, arr,
                  {"type": "equirect", "lat_top": lat_top, "lon_left": lon_left, "dlat": 1 / ppd, "dlon": 1 / ppd},
                  float(np.radians(1 / ppd) * R), {"source": str(img_path)})


# --------------------------------------------------------------------------
# Colour-coded slope image (LOLA polar map)
# --------------------------------------------------------------------------
def load_slope_image(path, name, body="moon", colat_edge=15.0, center=(992.5, 1216.5), r_px=845.0,
                     bar_row=62, bar_x0=92.5, px_per_unit=51.64, vmax=32.54, max_color_dist=40.0):
    """Decode a colour-mapped slope picture back to degrees using its own colour bar.

    Defaults match slope-75s-large-1.jpg (LOLA south-pole slope, 75S..90S): colour bar
    spans 0..32.54 deg, 51.64 px/deg starting at x=92.5.
    """
    from PIL import Image
    from scipy.spatial import cKDTree
    a = np.array(Image.open(path).convert("RGB")).astype("float32")
    xs = np.arange(int(bar_x0) + 3, int(bar_x0 + vmax * px_per_unit) - 3)
    lut_rgb = a[bar_row, xs]
    lut_val = (xs - bar_x0) / px_per_unit
    dist, idx = cKDTree(lut_rgb).query(a.reshape(-1, 3), k=1)
    val = lut_val[idx].reshape(a.shape[:2]).astype("float32")
    dist = dist.reshape(a.shape[:2])
    cx, cy = center
    yy, xx = np.indices(val.shape)
    inside = np.hypot(xx - cx, yy - cy) <= r_px
    val[(dist > max_color_dist) | ~inside] = np.nan
    val[:300] = np.where(inside[:300], val[:300], np.nan)
    # metres per pixel: stereographic scale at the rim, approximate
    R = BODY_RADIUS_KM[body] * 1000
    pix_m = 2 * R * np.tan(np.radians(colat_edge) / 2) / r_px
    return Raster(name, body, "slope", val,
                  {"type": "polar_south", "cx": cx, "cy": cy, "r_px": r_px, "colat_edge": colat_edge},
                  float(pix_m), {"source": str(path), "note": "slope decoded from colour bar"})


# --------------------------------------------------------------------------
# Binary STL height-field
# --------------------------------------------------------------------------
def load_stl_heightfield(path, name, body="mars", bbox=None, z_scale_m=1.0, pixel_m=None):
    """Rebuild a regular grid from a Mars-Trek-style STL.

    bbox = (lat_south, lat_north, lon_west, lon_east) if known; otherwise the raster is
    uncalibrated (georef 'none') and only usable by pixel coordinates.
    z_scale_m converts STL z units to metres (Trek exports are usually normalised).
    """
    b = Path(path).read_bytes()
    n = int(np.frombuffer(b[80:84], "<u4")[0])
    dt = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    v = np.frombuffer(b, dt, count=n, offset=84)["v"].reshape(-1, 3)
    xs, xi = np.unique(v[:, 0], return_inverse=True)
    ys, yi = np.unique(v[:, 1], return_inverse=True)
    grid = np.full((len(ys), len(xs)), np.nan, "float32")
    grid[yi, xi] = v[:, 2]
    grid = grid[::-1] * z_scale_m                      # north-up
    if bbox:
        s, nn, w, e = bbox
        g = {"type": "equirect", "lat_top": nn, "lon_left": w,
             "dlat": (nn - s) / grid.shape[0], "dlon": (e - w) / grid.shape[1]}
        pm = np.radians(g["dlat"]) * BODY_RADIUS_KM[body] * 1000
    else:
        g, pm = {"type": "none"}, float(pixel_m or 1000.0)
    return Raster(name, body, "dem", grid, g, pm, {"source": str(path), "calibrated": bool(bbox)})


def make_synthetic_dem(name="demo_synthetic_earth", body="earth", n=600, seed=0, bbox=(-30, -15, -75, -60)):
    """SYNTHETIC test terrain (fractal + ridge belt). For tests/demo only - not real data."""
    rng = np.random.default_rng(seed)
    f = np.fft.fftfreq(n)[:, None] ** 2 + np.fft.fftfreq(n)[None, :] ** 2
    f[0, 0] = 1
    z = np.fft.ifft2(np.fft.fft2(rng.normal(size=(n, n))) / f ** 0.9).real
    z = (z - z.min()) / np.ptp(z)
    yy, xx = np.mgrid[0:n, 0:n] / n
    belt = np.exp(-((yy - 0.35 - 0.3 * xx) ** 2) / 0.01)          # tilted mountain belt
    dem = 3000 * z * (0.3 + 3 * belt) + 4000 * belt
    s, nn, w, e = bbox
    g = {"type": "equirect", "lat_top": nn, "lon_left": w, "dlat": (nn - s) / n, "dlon": (e - w) / n}
    return Raster(name, body, "dem", dem.astype("float32"), g,
                  float(np.radians(g["dlat"]) * BODY_RADIUS_KM[body] * 1000), {"synthetic": True})
