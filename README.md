# ARES — Mars Mission Planning and Terrain Intelligence System

ARES (Mars Mission Planning and Terrain Intelligence System) is a Jezero
Crater terrain-intelligence and mission-planning dashboard. It presents a
processed HRSC/MOLA blended DEM slope product alongside an interactive,
deterministic route-scoring demonstration.

## Start locally

Prerequisites: Node.js and npm, plus Python with the Windows `py` launcher.
From the project directory, install the frontend dependencies and prepare the
backend environment once:

```powershell
npm ci
py -m venv .venv-geo
.\.venv-geo\Scripts\python.exe -m pip install fastapi uvicorn rasterio
```

Open two terminals in the project directory.

Terminal 1 — FastAPI terrain service:

```powershell
.\.venv-geo\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2 — Vite dashboard:

```powershell
npm run dev
```

Open the URL Vite prints (normally `http://localhost:5173`). The Vite dev
server forwards `/api` requests to `http://127.0.0.1:8000`. Set
`VITE_API_PROXY_TARGET` to override that backend address. For a separately
hosted frontend, set `VITE_API_BASE_URL` to the backend origin when building,
and set `ARES_CORS_ORIGINS` on the backend to a comma-separated list of
permitted frontend origins.

## Terrain API

- `GET /api/health` — API and processed-data availability.
- `GET /api/terrain/jezero/summary` — provenance and derived slope statistics.
- `GET /api/terrain/jezero/slope` — raster dimensions, CRS, resolution and
  bounds.
- `GET /api/terrain/jezero/slope/preview` — PNG visualization of the
  processed slope raster.
- `GET /api/terrain/jezero/slope/raster` — original processed GeoTIFF.

The source is the USGS-distributed *Mars MGS MOLA – MEX HRSC Blended DEM
Global 200m v2*, a 200 m/pixel blend of MOLA and HRSC elevation data. MOLA is
the Mars Orbiter Laser Altimeter on NASA's Mars Global Surveyor; HRSC is the
High Resolution Stereo Camera on ESA's Mars Express. This is a NASA–ESA blended
product published by USGS, not an exclusively NASA-produced dataset.

The derived slope raster is used for preliminary terrain/traversability
analysis around Jezero Crater. USGS metadata warns that some blends contain
artifacts and should be used with care for scientific analysis. The slope
analysis is therefore provisional, and its vertical units are marked
unverified.

### NASA data sources and attribution

> ARES uses the *Mars MGS MOLA – MEX HRSC Blended DEM Global 200m v2*, published
> by the USGS Astrogeology Science Center. It combines MOLA data from NASA's
> Mars Global Surveyor and HRSC data from ESA's Mars Express. The 200 m/pixel
> elevation product is processed to derive terrain slope for preliminary
> traversability analysis around Jezero Crater.

Recommended citation from the USGS product record:

> Fergason, R. L., Hare, T. M., & Laura, J. (2018). *HRSC and MOLA Blended
> Digital Elevation Model at 200m v2*. Astrogeology PDS Annex, U.S. Geological
> Survey.

- [USGS product record and downloads](https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m)
- Product record lists MOLA as CC0 and HRSC as CC BY-SA 3.0 IGO; consult the
  source record for component attribution and use conditions.

The product's NASA instrument contribution is not the same as the DEM being an
exact resource listed by the NASA Space Apps challenge. Do not describe this
DEM as sourced from Mars Trek or the USGS geologic map. Any connection to a
related Mars Trek catalog layer does not establish that this specific blended
DEM is included in the challenge's official Resources list; verify the exact
resource entry before making a challenge-compliance claim.

## Route-planning data limits

There is no backend route-planning or science-target endpoint in this project.
The three route candidates, their geometry, distances, durations, oxygen
reserves, slopes, hazards and objective scores are explicitly illustrative
scenario inputs. The client ranks these with a deterministic weighted score
and rejects any candidate that violates the configured duration, oxygen or
slope limits. The energy term is a distance/slope/duration proxy. None of these
route values are extracted from the terrain raster, NASA observations, or a
validated mission model.

The slope overlay and summary are loaded from the available processed backend
products; they are not substituted with generated map data.

## Checks

```powershell
npm run build
npm run lint
```
