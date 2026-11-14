# Data sources
* **Earth:** Copernicus GLO-90 DEM (AWS open data, `copernicus-dem-90m`), 1°×1° COG tiles. `scripts/download_earth.py`.
* **Mars:** MOLA MEGDR (NASA PDS Geosciences, `mgs-m-mola-5-megdr-l3-v1`). Your `meg016` tile is 16 px/deg (~3.7 km) – coarse;
  browse the `mgsl_300x/` directory for `meg032/064/128` (finer) and pass `--dir` / `--tile`.
  A GeoTIFF placed in `data/mars/` also works.
* **Moon:** LOLA products (PDS / Moon Trek / QuickMap). Included: your polar slope map. Any LOLA DEM GeoTIFF dropped in `data/moon/`
  can be registered by adding an entry to `config/datasets.json` (copy the Earth entry, set `"body": "moon"`).
* **Radar (optional, from your zips):** `eodms-cli` downloads RADARSAT imagery for Canadian analog sites (e.g. Haughton/Devon Island);
  SAR backscatter texture is a natural next feature (radar roughness is used for Moon/Mars via Mini-RF/SHARAD).
* Add a dataset: put the file under `data/`, add an entry in `config/datasets.json`, restart.
