# ARES — Mars Mission Planning and Terrain Intelligence System

ARES is a web-based terrain-intelligence and mission-planning dashboard for
preliminary rover-route assessment around Jezero Crater on Mars. It combines
processed MOLA–HRSC elevation data and derived terrain visualizations with an
interactive dashboard, illustrative route-scoring scenarios, and a
slope-grid A* route planner.

> **Scope:** ARES is a decision-support prototype, not an autonomous rover
> navigation system. The terrain slope product is derived from a real Mars
> elevation dataset. The dashboard's illustrative route candidates, geometry,
> and metrics are not measured traverses or georeferenced navigation paths;
> the separate terrain route planner calculates paths on the processed raster.

## Features

- Interactive Mars mission-planning dashboard with terrain and slope views.
- Processed Jezero slope raster, summary statistics, terrain provenance, and
  project-defined classification.
- Configurable science objective and duration, oxygen, and slope limits.
- Adjustable science, safety, time, and energy priorities.
- Deterministic ranking and feasibility checks for illustrative route scenarios.
- Separate backend A* path planning over the processed slope raster.
- Configurable project-defined slope classes and calculated-route terrain profiles.
- Provenance manifest and product checksum/metadata verification.
- Links to NASA and USGS Mars mapping and imagery resources.

Science-target locations and scores are not integrated; any such displayed
scenario markers and scores are illustrative, not NASA observations.

## Technology

| Area | Technologies |
| --- | --- |
| Frontend | React, TypeScript, Vite |
| Backend API | Python, FastAPI, Uvicorn |
| Raster/API access | Rasterio, NumPy, Pillow |
| Geospatial processing scripts | Rasterio, NumPy, SciPy, Pillow |
| Frontend/backend communication | HTTP via `/api` |

`package.json` and `package-lock.json` define the frontend dependencies.
There is no Python dependency manifest in this project; install the Python
packages using the commands below. The API runtime uses FastAPI, Uvicorn,
Rasterio, NumPy, and Pillow. SciPy is needed by the existing geospatial
processing scripts. The API does not require PyProj.

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
.\.venv-geo\Scripts\python.exe -m pip install fastapi uvicorn rasterio numpy pillow
```

To run the existing geospatial processing or preview scripts, also install
their additional imports:

```powershell
.\.venv-geo\Scripts\python.exe -m pip install scipy pillow
```

## Terrain data

ARES uses the USGS-distributed *Mars MGS MOLA – MEX HRSC Blended DEM Global
200m v2* (200 m/pixel). It combines:

- **MOLA:** Mars Orbiter Laser Altimeter data from NASA's Mars Global Surveyor.
- **HRSC:** High Resolution Stereo Camera data from ESA's Mars Express.

This is a NASA–ESA blended product published by the USGS Astrogeology Science
Center, not an exclusively NASA-produced dataset. The project checkout
contains these processed products under `backend/data/processed/`:

- `provenance.json` — source record, processing pipeline, product metadata and
  checksums for the committed/captured derivatives.
- `jezero_slope_deg.tif` — derived Jezero slope raster.
- `jezero_slope_preview.png` — preview image served by the API.
- `jezero_terrain_summary.json` — source and derived slope summary.
- `jezero_traversability_5_12_18.tif` — project-defined default slope classes,
  generated on demand from the processed slope raster.
- `jezero_traversability_5_12_18_preview.png` — visualization of those classes.

The original global DEM is not required to run the API when the processed
products are present. If they are missing, terrain endpoints report unavailable
data or return not found.

The original file inspected while preparing the manifest is named
`Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif`. Its header reports 106,694 ×
53,347 pixels, one Int16 band, geographic Mars 2000 Sphere coordinates,
0.003374120830641° pixel spacing, and NoData -32768. The USGS record gives the
product's nominal resolution as 200 m/pixel. This 11.38 GB file is outside the
project checkout; its SHA-256 was deliberately not calculated. The external
copy's presence and header metadata at manifest capture do not mean the source
DEM is packaged with ARES.

### Processing scripts

- `backend/geospatial/test_jezero_slope.py` extracts and processes the Jezero
  region and writes the slope raster and summary to `backend/data/processed/`.
  Its `SOURCE` constant currently points to a local DEM in a Downloads folder;
  update that path to the location of the source file before running the script.
- `backend/geospatial/render_slope_preview.py` creates
  `backend/data/processed/jezero_slope_preview.png` from the slope raster.

The scripts are separate from API startup; they are not run automatically by
the backend.

### Reproducing and checking products

The source DEM is large and not required for ordinary application startup.
To regenerate the Jezero slope and summary from a separately obtained source
file, first update the `SOURCE` path in
`backend/geospatial/test_jezero_slope.py`, then run from the project root:

```powershell
.\.venv-geo\Scripts\python.exe backend\geospatial\test_jezero_slope.py
.\.venv-geo\Scripts\python.exe backend\geospatial\render_slope_preview.py
```

Start FastAPI and request
`http://127.0.0.1:8000/api/terrain/jezero/traversability` to generate or
refresh the default 5°/12°/18° classified GeoTIFF and PNG preview. This
preserves the source slope raster and its grid.

Run this command to verify the manifest's checksums and raster/image metadata
for the listed local products:

```powershell
.\.venv-geo\Scripts\python.exe -m backend.provenance
```

It exits nonzero if a listed product is missing or differs from its manifest
checksum/metadata. Reprocessing a product changes its checksum; inspect the
new product and update the manifest only after reviewing its source, method,
parameters and metadata. The verifier hashes only the small processed
products; it does not read or hash the original global DEM. The timestamps for
existing products are filesystem modification-time observations because the
original slope product does not embed generation timestamps or historical
software versions.

The processing script uses bilinear reprojection onto a local stereographic
grid at 200 m, followed by a central-difference gradient
`degrees(atan(sqrt((dz/dx)^2 + (dz/dy)^2)))`. It excludes a one-cell boundary
around NoData. The script does not independently confirm vertical units before
applying the gradient; they remain explicitly unverified. Its slope output is
therefore provisional. The output CRS WKT has no authoritative EPSG identifier
recorded; ARES reports the embedded WKT rather than inferring an EPSG code.

### Data attribution and limitations

Recommended citation from the USGS product record:

> Fergason, R. L., Hare, T. M., & Laura, J. (2018). *HRSC and MOLA Blended
> Digital Elevation Model at 200m v2*. Astrogeology PDS Annex, U.S. Geological
> Survey.

- [USGS product record and downloads](https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m)
- The product record lists MOLA as CC0 and HRSC as CC BY-SA 3.0 IGO. Consult
  the source record for component attribution and use conditions.

The USGS product page identifies the publisher, instruments, contributing
missions, publication date (2018-01-31), product resolution, and recommended
citation. No separate product identifier is listed there, so the manifest
records it as unknown. The global product page is the source citation; NASA
resource links elsewhere in the dashboard are not asserted as the download
source for this DEM.

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

If port 8000 is already in use, start FastAPI on port 8001 and point Vite's
proxy at it:

```powershell
.\.venv-geo\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8001
$env:VITE_API_PROXY_TARGET = "http://127.0.0.1:8001"
npm run dev -- --port 5174
```

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
| `GET /api/health` | API status, processed terrain availability, and whether the backend exposes A* route planning. |
| `GET /api/provenance` | Manifest plus availability, SHA-256, and metadata verification for local products. The original global DEM is not checksummed. |
| `GET /api/terrain/jezero/summary` | Source provenance and derived slope statistics from the processed JSON summary. |
| `GET /api/terrain/jezero/slope` | Raster dimensions, resolution, CRS, bounds, and band metadata. |
| `GET /api/terrain/jezero/slope/preview` | PNG preview of the processed slope raster. |
| `GET /api/terrain/jezero/slope/raster` | Processed GeoTIFF slope raster. |
| `GET /api/terrain/jezero/traversability` | Class counts, percentages, raster metadata, and derived-product links. Accepts `low_slope_max_degrees`, `moderate_slope_max_degrees`, and `high_slope_max_degrees` query parameters. |
| `GET /api/terrain/jezero/traversability/preview` | RGBA preview of the classified raster. |
| `GET /api/terrain/jezero/traversability/raster` | Classified uint8 GeoTIFF aligned to the source slope raster. |
| `POST /api/route/plan` | A* route over traversable cells in the processed slope raster, including a route-cell slope profile. |

`GET /api/provenance` returns HTTP 503 when the manifest is missing or invalid.
Product integrity checks run on this endpoint and through the command-line
verifier; ordinary route planning does not calculate product checksums.
Terrain-summary and route responses include compact provenance references
without changing their existing result fields.
The frontend expects `/api/health` to include `route_planning_available: true`
before enabling route calculations, so an older or mismatched backend can be
distinguished from a working route-planning service. Frontend API requests
time out after 15 seconds and report the failure rather than remaining in a
loading state indefinitely.

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

The API derives a separate classified GeoTIFF from the processed slope raster
on first request and refreshes it when the source raster changes. Class codes
are 1 (low), 2 (moderate), 3 (high), and 4 (above the configured upper
threshold); 0 is NoData. Default upper thresholds are 5°, 12°, and 18°.
Thresholds can be overridden on the traversability endpoints, subject to
`0 <= low < moderate < high <= 90`. Upper boundaries are inclusive, so exactly
5° is low, exactly 12° is moderate, and exactly 18° is high. The derived raster
and PNG preview are written under `backend/data/processed/`; the source slope
raster is not modified.

These are ARES project categories, not NASA-certified rover-safety limits.
Class percentages exclude NoData cells. The route response reports slopes at
the actual calculated path cells. Route-edge distance is assigned to the more
severe class of its two endpoint cells; contiguous high-slope segments are
consecutive route cells above the profile's moderate-class upper threshold.
Slope alone does not establish physical traversability or account for rocks,
wheel slip, soil, subsurface conditions, or rover-specific limits.

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

### Terrain-based backend route planner

The dashboard's **Terrain Route Planner** uses `POST /api/route/plan` without
replacing the illustrative route candidates. On the slope-map layer, select
map locations for the rover start and science destination, then calculate.
Map clicks are transformed to raster cell centers using the image's matching
851 × 891 dimensions and the raster metadata bounds. The frontend submits
coordinates already converted to the embedded projected CRS; no external
coordinate transformation is performed.

The endpoint accepts `start` and `destination` as
`{ "x": ..., "y": ... }` points, `max_slope_degrees` (greater than 0 and at
most 90), and `slope_penalty` from 0 to 100. The response includes route
coordinates at cell centers, path distance, slope statistics, the embedded
raster CRS, a slope-weighted movement cost, and a terrain profile calculated
from the actual route cells. Optional `low_slope_max_degrees`,
`moderate_slope_max_degrees`, and `high_slope_max_degrees` fields configure the
profile categories and use the same validated thresholds as the
traversability API. Invalid endpoints and unreachable routes return HTTP 422;
unavailable or unsuitable raster data returns HTTP 503. Changing the
maximum-slope or penalty setting marks an already calculated route as stale
until it is recalculated.

The planner uses 8-directional A* over finite, nonnegative slope cells. Cells
above the requested maximum slope and NoData cells are blocked; diagonal steps
are allowed only when both adjacent orthogonal cells are traversable. Each
step's cost is

`distance_m × (1 + slope_penalty × (mean_endpoint_slope / max_slope)²)`.

The straight-line projected distance heuristic is admissible because the
slope multiplier is never less than one. The raster is cached in memory and a
search is capped at 200,000 expanded cells. Movement cost is a
slope-weighted metre-equivalent, not energy consumption or mission duration.
This provisional 200 m/pixel, slope-only result does not establish rover
safety, physical traversability, or validated navigation.

## Data & methodology disclosure

The provenance manifest is `backend/data/processed/provenance.json`. It records
the verified USGS source record, source raster header facts observed during
manifest capture, processing steps and assumptions, product metadata and
checksums, and explicit unknown or unverified values. `GET /api/provenance`
returns this manifest alongside availability and verification status for the
local derivatives. It verifies local outputs against their recorded checksums
and selected raster/image metadata; it does not checksum the 11.38 GB global
source file.

The dashboard's collapsible **Data & Methodology** panel presents this source,
processing summary, classification boundaries, route-cost meaning, scientific
limitations, citation, and product-integrity status. If the manifest or API is
unavailable, the panel reports that status rather than treating missing
metadata as verified.

**AI-assisted development disclosure:** A Copilot-based AI assistant in VS Code
assisted with software implementation, debugging, test authoring, quality
checks, and technical documentation. At runtime, ARES does not call a
generative-AI service. Illustrative scoring and the commander text response
use deterministic local logic; terrain routes are calculated by the FastAPI
backend from processed raster data. The repository does not establish whether
`src/assets/hero.png` or other visual assets were AI-generated, so their origin
must be confirmed by the project team before making an originality or
AI-generation claim. Project authors remain responsible for reviewing the
code, sources, and scientific claims. This disclosure does not imply NASA
authorship, endorsement, validation, or challenge-rule compliance. Check the
selected challenge's current official AI-disclosure instructions and complete
any required submission-field disclosure separately.

## Project structure

```text
.
├── backend/
│   ├── data/processed/
│   │   ├── provenance.json
│   │   ├── jezero_slope_deg.tif
│   │   ├── jezero_slope_preview.png
│   │   ├── jezero_terrain_summary.json
│   │   ├── jezero_traversability_5_12_18.tif   # Generated on request
│   │   └── jezero_traversability_5_12_18_preview.png
│   ├── geospatial/
│   │   ├── render_slope_preview.py
│   │   └── test_jezero_slope.py
│   ├── tests/
│   │   ├── test_pathfinding.py
│   │   ├── test_terrain_classification.py
│   │   └── test_provenance.py
│   ├── main.py
│   ├── pathfinding.py
│   ├── provenance.py
│   └── terrain_classification.py
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

Run the backend unit tests with:

```powershell
.\.venv-geo\Scripts\python.exe -m unittest discover -s backend\tests
```
