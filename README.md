# Analog Finder – terrestrial analogs for Moon / Mars station sites

**Challenge:** use open Earth, Moon and Mars data to find and characterise terrestrial analogs
(deserts, polar regions, volcanic terrain, craters…) for future bases or landing sites, and present the
result as a map / tool.

**What this project does:** you click (or type) a place – e.g. the Andes – and it finds regions on
*every loaded body* whose terrain character is similar, ranks them as candidate sites, and scores how
buildable each area is for a surface station. It runs fully offline in your browser.

```
analog-finder/
├─ backend/analogfinder/   raster loaders · features · similarity · Flask API · CLI
├─ frontend/index.html     interactive map UI (no CDN, works offline)
├─ config/                 datasets.json (what to load) · known_analogs.json (Atacama, Haughton, …)
├─ scripts/                download_earth.py · download_mars.py · convert_mola.py · import_trek_stl.py · make_demo_data.py
├─ data/{earth,moon,mars,samples}/
├─ docs/                   METHODS.md · DATA.md · ui_screenshot.png
├─ tests/                  pytest (6 tests)
└─ outputs/                example result (Moon south pole query)
```

## Quick start
```bash
pip install -r requirements.txt
python scripts/make_demo_data.py            # SYNTHETIC test terrain (flagged in the UI) – optional
cd backend && python -m analogfinder.server  # open http://127.0.0.1:8000
# or command line:
PYTHONPATH=backend python -m analogfinder query --lat -80 --lon 0 --radius 30 --out outputs/my_query
PYTHONPATH=backend python -m analogfinder status   # which datasets are loaded
pytest tests
```

## Deploy online with Render

The project includes a Render Blueprint (`render.yaml`) to deploy the Flask API and
frontend together. To publish it:

1. Push the contents of this project folder to a GitHub repository.
2. In Render, choose **New → Blueprint**, connect GitHub, and select that repository.
3. Review the `analog-finder` web service and choose **Apply**. Render will install
   `requirements.txt` and publish the site; open the `onrender.com` URL shown on the
   service page after deployment finishes.

The frontend uses relative API URLs, so it works from the deployed site without a
separate frontend host. Each push to the connected branch triggers a redeploy.

Only datasets present in the repository are available online. With the included
files, that is the real Moon slope map and the clearly marked synthetic Earth demo;
real Earth and Mars data are not included. To publish those datasets too, fetch them
locally first and include them in the repository (large raster files can exceed
GitHub's file-size limits; use Git LFS or persistent storage if needed).

### Deploy with Vercel

The `pyproject.toml` file identifies the Flask app entrypoint for Vercel. Import the
GitHub repository in Vercel and deploy from the project root; keep the Python
dependencies in `requirements.txt`.

## Get real data (one command, run on your own machine)
This project was built in a sandbox whose network policy blocks every data host, so **no real Earth or Mars
elevation data is inside the zip**. On a normal internet connection:
```bash
pip install -r requirements.txt
python scripts/fetch_all_data.py                 # Earth (Andes tiles) + Mars MOLA + Moon LOLA, converted automatically
python scripts/fetch_all_data.py --only earth --preset atacama
python scripts/fetch_all_data.py --mars-res 64 --moon-res 64   # finer, bigger downloads
cd backend && python -m analogfinder.server      # open http://127.0.0.1:8000, query -22.5, -67.5
```
Each step reports failures and continues. If a PDS filename differs, download manually (see `docs/DATA.md`) and
run `scripts/convert_mola.py <img> <lbl>`. Earthdata/Copernicus Data Space/RCM sources need free logins and are optional extras.

## What is real here
| Dataset | Status |
|---|---|
| Moon – LOLA south-pole slope map (your `slope-75s-large-1.jpg`) | **Real**, decoded back to degrees from its colour bar; georeferenced as polar stereographic 75°S–90°S |
| Earth – Copernicus GLO-90 | Real once downloaded (script provided) |
| Mars – MOLA | Real once downloaded (script provided) |
| Mars Trek STL (`trekSTL.stl`) | 400×400 height grid with **no coordinates and normalised heights**; loader included, but you must supply the lat/lon box and vertical scale (`scripts/import_trek_stl.py`) |
| `demo_synthetic_earth` | **Synthetic** fractal terrain for testing only; labelled in UI/plots. Do not draw conclusions from it |

## Honest limitations
* "Tectonic structure" is approximated by **lineament coherence and edge density** of the slope field.
  It does not use geology, faults or crustal age – add geologic maps for that.
* Suitability weights (flat, smooth, few scarps) are simple assumptions, not NASA siting criteria.
  Real siting also needs illumination, comms, resources (ice, water), radiation and landing ellipses.
* The Moon dataset is slope-only, so only slope-derived features are compared; DEM-only features
  (relief) are used only when every dataset is a DEM.
* Polar-stereographic cell areas are approximate.
* Known analog coordinates are approximate.
See `docs/METHODS.md`.
