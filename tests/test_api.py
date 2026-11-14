import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from analogfinder.server import app


def test_status_and_query():
    c = app.test_client()
    s = c.get("/api/status").get_json()
    assert any(d["status"] == "ok" for d in s["datasets"])
    r = c.post("/api/query", json={"lat": -80, "lon": 0, "radius_km": 30}).get_json()
    assert "datasets" in r and r["query"]["dataset"] == "moon_lola_south_slope"
    bad = c.post("/api/query", json={"lat": 10, "lon": 10})
    assert bad.status_code == 400
