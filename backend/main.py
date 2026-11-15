
import json
import os
from pathlib import Path

import rasterio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

app = FastAPI(
    title="ARES Mars Mission API",
    description="Geospatial terrain and mission-planning services.",
    version="0.2.0",
)

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "ARES_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data" / "processed"

SUMMARY_FILE = DATA_DIR / "jezero_terrain_summary.json"
SLOPE_FILE = DATA_DIR / "jezero_slope_deg.tif"
PREVIEW_FILE = DATA_DIR / "jezero_slope_preview.png"

@app.get("/api/health")
def health():
    data_available = SUMMARY_FILE.exists() and SLOPE_FILE.exists()

    return {
        "status": "ok",
        "data_status": "connected" if data_available else "not_connected",
        "message": (
            "Jezero terrain products are available."
            if data_available
            else "Terrain products have not been generated."
        ),
    }


@app.get("/api/terrain/jezero/summary")
def terrain_summary():
    if not SUMMARY_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail="Jezero terrain summary not found.",
        )

    with open(SUMMARY_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


@app.get("/api/terrain/jezero/slope")
def slope_metadata():
    if not SLOPE_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail="Jezero slope raster not found.",
        )

    with rasterio.open(SLOPE_FILE) as src:
        return {
            "region": "Jezero Crater",
            "width": src.width,
            "height": src.height,
            "resolution": {
                "x": src.res[0],
                "y": src.res[1],
                "unit": "metres",
            },
            "crs": src.crs.to_string(),
            "bounds": {
                "left": src.bounds.left,
                "bottom": src.bounds.bottom,
                "right": src.bounds.right,
                "top": src.bounds.top,
            },
            "nodata": src.nodata,
            "band_description": src.descriptions[0],
            "raster_url": "/api/terrain/jezero/slope/raster",
        }


@app.get("/api/terrain/jezero/slope/raster")
def slope_raster():
    if not SLOPE_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail="Jezero slope raster not found.",
        )

    return FileResponse(
        path=SLOPE_FILE,
        media_type="image/tiff",
        filename="jezero_slope_deg.tif",
    )


@app.get("/api/terrain/jezero/slope/preview")
def slope_preview():
    if not PREVIEW_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail="Jezero slope preview not found.",
        )

    return FileResponse(
        path=PREVIEW_FILE,
        media_type="image/png",
        headers={"Content-Disposition": "inline"},
    )