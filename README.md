# ARES — Mars Mission Planning and Terrain Intelligence System

ARES is a web-based terrain-intelligence and mission-planning dashboard for
preliminary rover-route assessment around Jezero Crater on Mars. It combines
processed MOLA–HRSC elevation data and a derived slope visualization with an
interactive dashboard and deterministic route-scoring demonstration.

> **Scope:** ARES is a decision-support prototype, not an autonomous rover
> navigation system. The terrain slope product is derived from a real Mars
> elevation dataset. Route candidates, their geometry, and their metrics are
> illustrative scenarios, not measured traverses or georeferenced navigation
> paths.

## Features

- Interactive Mars mission-planning dashboard with terrain and slope views.
- Processed Jezero slope raster, summary statistics, and terrain provenance.
- Configurable science objective and duration, oxygen, and slope limits.
- Adjustable science, safety, time, and energy priorities.
- Deterministic ranking and feasibility checks for illustrative route scenarios.
- Links to NASA and USGS Mars mapping and imagery resources.

Science-target locations and scores are not integrated; any such displayed
scenario markers and scores are illustrative, not NASA observations.

## Technology

| Area | Technologies |
| --- | --- |
| Frontend | React, TypeScript, Vite |
| Backend API | Python, FastAPI, Uvicorn |
| Raster/API access | Rasterio |
| Geospatial processing scripts | Rasterio, NumPy, SciPy, Pillow |
| Frontend/backend communication | HTTP via `/api` |

`package.json` and `package-lock.json` define the frontend dependencies.
There is no Python dependency manifest in this project; install the Python
packages using the commands below. The API runtime uses FastAPI, Uvicorn, and
Rasterio. NumPy, SciPy, and Pillow are needed by the existing geospatial
processing and preview scripts. The API itself does not import PyProj.

## Prerequisites

- Node.js `^20.19.0` or `>=22.12.0` and npm, as required by the installed Vite
  version.
- Python 3 and the Windows `py` launcher.
- Git only if cloning the repository.

Commands below use Windows PowerShell and assume they are run from the project
root (the directory containing `package.json`).

## Installation

Install the JavaScript dependencies and create a virtual environment for the
Python backend:

```powershell
npm ci
py -m venv .venv-geo
```

Install the API runtime dependencies:

```powershell
.\.venv-geo\Scripts\python.exe -m pip install --upgrade pip
.\.venv-geo\Scripts\python.exe -m pip install fastapi uvicorn rasterio
```

To run the existing geospatial processing or preview scripts, also install
their additional imports:

```powershell
.\.venv-geo\Scripts\python.exe -m pip install numpy scipy pillow
```

## Terrain data

ARES uses the USGS-distributed *Mars MGS MOLA – MEX HRSC Blended DEM Global
200m v2* (200 m/pixel). It combines:

- **MOLA:** Mars Orbiter Laser Altimeter data from NASA's Mars Global Surveyor.
- **HRSC:** High Resolution Stereo Camera data from ESA's Mars Express.

This is a NASA–ESA blended product published by the USGS Astrogeology Science
Center, not an exclusively NASA-produced dataset. The project checkout
contains these processed products under `backend/data/processed/`:

- `jezero_slope_deg.tif` — derived Jezero slope raster.
- `jezero_slope_preview.png` — preview image served by the API.
- `jezero_terrain_summary.json` — source and derived slope summary.

The original global DEM is not required to run the API when the processed
products are present. If they are missing, terrain endpoints report unavailable
data or return not found.

### Processing scripts

- `backend/geospatial/test_jezero_slope.py` extracts and processes the Jezero
  region and writes the slope raster and summary to `backend/data/processed/`.
  Its `SOURCE` constant currently points to a local DEM in a Downloads folder;
  update that path to the location of the source file before running the script.
- `backend/geospatial/render_slope_preview.py` creates
  `backend/data/processed/jezero_slope_preview.png` from the slope raster.

The scripts are separate from API startup; they are not run automatically by
the backend.

### Data attribution and limitations

Recommended citation from the USGS product record:

> Fergason, R. L., Hare, T. M., & Laura, J. (2018). *HRSC and MOLA Blended
> Digital Elevation Model at 200m v2*. Astrogeology PDS Annex, U.S. Geological
> Survey.

- [USGS product record and downloads](https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m)
- The product record lists MOLA as CC0 and HRSC as CC BY-SA 3.0 IGO. Consult
  the source record for component attribution and use conditions.

USGS metadata warns that some blended regions contain artifacts and should be
used carefully for scientific analysis. The Jezero slope analysis is
provisional; vertical units are marked unverified, and the result is not
validated for mission use. The slope values are derived from the blended DEM,
not direct NASA observations.

NASA-related resource links for further reference:

- [NASA JPL Mars Trek](https://trek.nasa.gov/mars/)
- [USGS–NASA Interactive Mars Geologic Maps](https://astrogeology-usgs.hub.arcgis.com/pages/interactive-maps-mars)
- [Perseverance Raw Images](https://mars.nasa.gov/mars2020/multimedia/raw-images/)

These links do not imply that the blended DEM was downloaded from those
portals. A NASA instrument contribution does not by itself establish that this
specific product appears in the NASA Space Apps challenge's official
Resources list; verify that list before making a challenge-compliance claim.
Do not attribute this DEM to Mars Trek or the USGS geologic map.

## Start the application

Start the backend and frontend in separate terminals from the project root.

### Terminal 1: FastAPI backend

```powershell
.\.venv-geo\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

The API is available at `http://127.0.0.1:8000`; its interactive API
documentation is at `http://127.0.0.1:8000/docs`.

### Terminal 2: Vite frontend

```powershell
npm run dev
```

Open the URL Vite prints (normally `http://localhost:5173`). The Vite
development server proxies `/api` requests to `http://127.0.0.1:8000`.

## Environment configuration

Defaults work for local development. Set these variables only when changing
the default frontend/backend deployment addresses:

| Variable | Purpose |
| --- | --- |
| `VITE_API_PROXY_TARGET` | Overrides the backend origin used by Vite's `/api` development proxy. |
| `VITE_API_BASE_URL` | Sets the backend origin used by a separately hosted frontend build. |
| `ARES_CORS_ORIGINS` | Comma-separated allowed frontend origins for FastAPI. Defaults to `http://localhost:5173,http://127.0.0.1:5173`. |

For a separately hosted frontend, configure `VITE_API_BASE_URL` at build time
and add the frontend origin to `ARES_CORS_ORIGINS` for the backend.

## Terrain API

The FastAPI application in `backend/main.py` exposes:

| Endpoint | Description |
| --- | --- |
| `GET /api/health` | API status and availability of processed terrain data. |
| `GET /api/terrain/jezero/summary` | Source provenance and derived slope statistics from the processed JSON summary. |
| `GET /api/terrain/jezero/slope` | Raster dimensions, resolution, CRS, bounds, and band metadata. |
| `GET /api/terrain/jezero/slope/preview` | PNG preview of the processed slope raster. |
| `GET /api/terrain/jezero/slope/raster` | Processed GeoTIFF slope raster. |

The dashboard presents readable raster dimensions, source resolution, slope
method, valid cell count, and slope units; it does not display raw CRS/WKT
strings. The API metadata endpoint still returns its existing CRS and bounds
fields.

## Terrain analysis

The existing processing script extracts an approximate Jezero region from the
global blended DEM, reprojects it to a local Mars stereographic grid at 200 m
resolution, and computes slope with a central-difference gradient. Slope is
expressed in degrees. The preview script classifies pixels into four
visualization bands: 0–5°, 5–12°, 12–18°, and above 18°.

This is preliminary terrain analysis, not a validated assessment of rover
traversability or route safety. Vertical units remain unverified.

## Route-scoring demonstration

The frontend contains three illustrative route candidates. Its deterministic
weighted score ranks them according to the selected objective and science,
safety, time, and energy priorities. It marks candidates infeasible when they
exceed the configured maximum duration or slope, or fall below the configured
minimum oxygen reserve. The energy score is a distance/slope/duration proxy.

Route geometry, distances, durations, oxygen reserves, slopes, hazards, and
objective scores are synthetic scenario inputs. They are not extracted from
the terrain raster, NASA observations, rover telemetry, or a validated Mars
mission model. Routes are conceptual scenarios—not validated rover traverses
or georeferenced navigation paths. Science-target data is not integrated;
displayed target positions and scores are illustrative, not measured
observations.

## Project structure

```text
.
├── backend/
│   ├── data/processed/
│   │   ├── jezero_slope_deg.tif
│   │   ├── jezero_slope_preview.png
│   │   └── jezero_terrain_summary.json
│   ├── geospatial/
│   │   ├── render_slope_preview.py
│   │   └── test_jezero_slope.py
│   └── main.py
├── public/
│   ├── favicon.svg
│   └── icons.svg
├── src/
│   ├── services/
│   │   ├── missionPlanner.ts
│   │   └── terrainApi.ts
│   ├── assets/
│   ├── App.css
│   ├── App.tsx
│   ├── index.css
│   ├── main.tsx
│   └── styles.css
├── .gitignore
├── eslint.config.js
├── index.html
├── package-lock.json
├── package.json
├── tsconfig.app.json
├── tsconfig.json
├── tsconfig.node.json
└── vite.config.ts
```

## Checks

Run these commands from the project root:

```powershell
npm run build
npm run lint
```
