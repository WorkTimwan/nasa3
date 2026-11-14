import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from analogfinder.raster import Raster, make_synthetic_dem, load_stl_heightfield
from analogfinder.features import compute_features
from analogfinder.similarity import common_features, robust_scaler, query_vector, search

STL = Path("/mnt/user-data/attachments/4d835d30-415a-55a3-b36b-26630d61c99a/544a338d-trekSTL.stl")


def test_equirect_roundtrip():
    r = make_synthetic_dem(n=100)
    rr, cc = r.latlon_to_rc(-22.5, -67.5)
    lat, lon = r.rc_to_latlon(rr, cc)
    assert abs(lat + 22.5) < 1e-6 and abs(lon + 67.5) < 1e-6


def test_polar_roundtrip():
    g = {"type": "polar_south", "cx": 100, "cy": 100, "r_px": 80, "colat_edge": 15}
    r = Raster("m", "moon", "slope", np.zeros((200, 200), "float32"), g, 500)
    rr, cc = r.latlon_to_rc(-82.0, 40.0)
    lat, lon = r.rc_to_latlon(rr, cc)
    assert abs(lat + 82) < 1e-6 and abs(lon - 40) < 1e-6


def test_slope_of_plane():
    n = 200
    g = {"type": "equirect", "lat_top": 1, "lon_left": 0, "dlat": 0.01, "dlon": 0.01}
    pm = np.radians(0.01) * 6371000
    z = (np.arange(n)[None, :] * pm * np.tan(np.radians(10))).repeat(n, 0).astype("float32")  # 10 deg plane
    r = Raster("p", "earth", "dem", z, g, pm)
    st = compute_features(r, scale_m=pm, window_km=3)
    s = st.cube[..., st.names.index("slope_mean")]
    assert abs(np.nanmedian(s) - 10) < 0.5


def test_self_similarity_is_high():
    r = make_synthetic_dem(n=300)
    st = compute_features(r, 3000, 30)
    names = common_features([st])
    med, iqr = robust_scaler([st], names)
    lat, lon = -22.5, -67.5
    qv, _ = query_vector(st, lat, lon, 40, names)
    sim, sites = search(st, qv, names, med, iqr, pct=5, min_area_km2=1)
    ri, ci = r.latlon_to_rc(lat, lon)
    f = st.scale_m / r.pixel_m
    assert sim[int(ri / f), int(ci / f)] > 0.8 and sites


def test_stl_loader():
    if not STL.exists():
        return
    r = load_stl_heightfield(STL, "t")
    assert r.shape == (400, 400) and r.georef["type"] == "none"


def test_pds_reader_lsb_and_msb(tmp_path):
    """Round-trips a tiny SYNTHETIC PDS3 file in both byte orders (loader test only)."""
    from analogfinder.raster import load_pds_img
    z = (np.arange(8 * 16).reshape(8, 16) - 30).astype("int16")
    for tag, dt in (("MSB_INTEGER", ">i2"), ("LSB_INTEGER", "<i2")):
        (tmp_path / "t.img").write_bytes(z.astype(dt).tobytes())
        (tmp_path / "t.lbl").write_text(f"LINES = 8\nLINE_SAMPLES = 16\nSAMPLE_BITS = 16\nSAMPLE_TYPE = {tag}\n"
                                        "MAP_RESOLUTION = 0.0444 <PIXEL/DEGREE>\nSCALING_FACTOR = 0.5\nOFFSET = 0\n")
        r = load_pds_img(tmp_path / "t.img", tmp_path / "t.lbl", "x", "moon")
        assert np.allclose(r.data, z * 0.5)
