
import json
import os
from pathlib import Path
from time import perf_counter

import rasterio
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.pathfinding import (
    PathPlanningError,
    RasterDataError,
    get_cached_grid,
    plan_route,
)
from backend.provenance import (
    DEFAULT_PROCESSED_DIR,
    MANIFEST_FILENAME,
    ProvenanceError,
    build_provenance_report,
    route_provenance_references,
)
from backend.terrain_classification import (
    ClassificationThresholds,
    TerrainClassificationError,
    build_route_terrain_profile,
    category_definitions,
    ensure_classification_product,
)

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
PROVENANCE_FILE = DEFAULT_PROCESSED_DIR / MANIFEST_FILENAME


class ProjectedCoordinate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)


class RoutePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: ProjectedCoordinate
    destination: ProjectedCoordinate
    max_slope_degrees: float = Field(gt=0, le=90, allow_inf_nan=False)
    slope_penalty: float = Field(ge=0, le=100, allow_inf_nan=False)
    low_slope_max_degrees: float = Field(
        default=5,
        ge=0,
        le=90,
        allow_inf_nan=False,
    )
    moderate_slope_max_degrees: float = Field(
        default=12,
        gt=0,
        le=90,
        allow_inf_nan=False,
    )
    high_slope_max_degrees: float = Field(
        default=18,
        gt=0,
        le=90,
        allow_inf_nan=False,
    )

    @model_validator(mode="after")
    def validate_classification_thresholds(self) -> "RoutePlanRequest":
        ClassificationThresholds(
            low_max_degrees=self.low_slope_max_degrees,
            moderate_max_degrees=self.moderate_slope_max_degrees,
            high_max_degrees=self.high_slope_max_degrees,
        )
        return self


class TraversabilityCategoryResponse(BaseModel):
    code: int
    name: str
    minimum_exclusive_degrees: float | None
    maximum_inclusive_degrees: float | None
    color: str
    cell_count: int
    percentage_of_valid_cells: float


class TraversabilityResponse(BaseModel):
    width: int
    height: int
    crs: str
    resolution: dict[str, float | str]
    transform: list[float]
    category_definitions: list[TraversabilityCategoryResponse]
    valid_cell_count: int
    nodata_cell_count: int
    analysis_metadata: dict[str, object]
    raster_url: str
    preview_url: str


class RoutePlanResponse(BaseModel):
    feasible: bool
    route_coordinates: list[ProjectedCoordinate]
    path_distance_m: float
    path_cell_count: int
    maximum_encountered_slope_degrees: float
    average_encountered_slope_degrees: float
    estimated_terrain_movement_cost: float = Field(
        description=(
            "Slope-weighted metre-equivalent cost; not a physical energy or "
            "mission-duration estimate."
        )
    )
    computation_time_ms: float
    coordinate_reference_system: str
    scientific_limitation: str
    terrain_profile: dict[str, object]
    provenance: dict[str, object]


def _classification_thresholds(
    low_slope_max_degrees: float,
    moderate_slope_max_degrees: float,
    high_slope_max_degrees: float,
) -> ClassificationThresholds:
    try:
        return ClassificationThresholds(
            low_max_degrees=low_slope_max_degrees,
            moderate_max_degrees=moderate_slope_max_degrees,
            high_max_degrees=high_slope_max_degrees,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error


def _classification_product(thresholds: ClassificationThresholds):
    try:
        return ensure_classification_product(
            SLOPE_FILE,
            DATA_DIR,
            thresholds,
        )
    except TerrainClassificationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error


def _classification_urls(thresholds: ClassificationThresholds) -> tuple[str, str]:
    query = (
        f"?low_slope_max_degrees={thresholds.low_max_degrees}"
        f"&moderate_slope_max_degrees={thresholds.moderate_max_degrees}"
        f"&high_slope_max_degrees={thresholds.high_max_degrees}"
    )
    return (
        f"/api/terrain/jezero/traversability/raster{query}",
        f"/api/terrain/jezero/traversability/preview{query}",
    )


@app.get("/api/health")
def health():
    data_available = (
        SUMMARY_FILE.exists()
        and SLOPE_FILE.exists()
        and PREVIEW_FILE.exists()
    )

    return {
        "status": "ok",
        "data_status": "connected" if data_available else "not_connected",
        "route_planning_available": True,
        "message": (
            "Jezero terrain products are available."
            if data_available
            else "Terrain products have not been generated."
        ),
    }


@app.get("/api/provenance")
def provenance():
    try:
        return build_provenance_report(PROVENANCE_FILE, DATA_DIR)
    except ProvenanceError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error


@app.get("/api/terrain/jezero/summary")
def terrain_summary():
    if not SUMMARY_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail="Jezero terrain summary not found.",
        )

    with open(SUMMARY_FILE, "r", encoding="utf-8") as file:
        summary = json.load(file)
    summary["provenance"] = route_provenance_references(PROVENANCE_FILE)
    return summary


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
            "provenance": route_provenance_references(PROVENANCE_FILE),
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


@app.get("/api/terrain/jezero/traversability", response_model=TraversabilityResponse)
def jezero_traversability(
    low_slope_max_degrees: float = Query(default=5, ge=0, le=90),
    moderate_slope_max_degrees: float = Query(default=12, gt=0, le=90),
    high_slope_max_degrees: float = Query(default=18, gt=0, le=90),
):
    thresholds = _classification_thresholds(
        low_slope_max_degrees,
        moderate_slope_max_degrees,
        high_slope_max_degrees,
    )
    product = _classification_product(thresholds)
    raster_url, preview_url = _classification_urls(thresholds)
    definitions = category_definitions(thresholds)
    categories = [
        TraversabilityCategoryResponse(
            **definition,
            cell_count=product.category_counts[int(definition["code"])],
            percentage_of_valid_cells=(
                product.category_counts[int(definition["code"])]
                / product.valid_cell_count
                * 100
            ),
        )
        for definition in definitions
    ]

    return TraversabilityResponse(
        width=product.width,
        height=product.height,
        crs=product.crs,
        resolution={
            "x": product.resolution[0],
            "y": product.resolution[1],
            "unit": "metres",
        },
        transform=list(product.transform),
        category_definitions=categories,
        valid_cell_count=product.valid_cell_count,
        nodata_cell_count=product.nodata_cell_count,
        analysis_metadata={
            "source": SLOPE_FILE.name,
            "classification_method": (
                "Project-defined categories derived from the source slope raster."
            ),
            "analysis_status": "provisional",
            "vertical_units_verified": False,
            "thresholds_degrees": {
                "low_max": thresholds.low_max_degrees,
                "moderate_max": thresholds.moderate_max_degrees,
                "high_max": thresholds.high_max_degrees,
            },
            "threshold_boundary_rule": (
                "Upper bounds are inclusive; lower bounds above zero are exclusive."
            ),
            "safety_limitation": (
                "Slope class does not establish physical rover traversability or safety."
            ),
            "provenance": route_provenance_references(PROVENANCE_FILE),
        },
        raster_url=raster_url,
        preview_url=preview_url,
    )


@app.get("/api/terrain/jezero/traversability/raster")
def traversability_raster(
    low_slope_max_degrees: float = Query(default=5, ge=0, le=90),
    moderate_slope_max_degrees: float = Query(default=12, gt=0, le=90),
    high_slope_max_degrees: float = Query(default=18, gt=0, le=90),
):
    thresholds = _classification_thresholds(
        low_slope_max_degrees,
        moderate_slope_max_degrees,
        high_slope_max_degrees,
    )
    product = _classification_product(thresholds)
    return FileResponse(
        path=product.raster_path,
        media_type="image/tiff",
        filename=product.raster_path.name,
    )


@app.get("/api/terrain/jezero/traversability/preview")
def traversability_preview(
    low_slope_max_degrees: float = Query(default=5, ge=0, le=90),
    moderate_slope_max_degrees: float = Query(default=12, gt=0, le=90),
    high_slope_max_degrees: float = Query(default=18, gt=0, le=90),
):
    thresholds = _classification_thresholds(
        low_slope_max_degrees,
        moderate_slope_max_degrees,
        high_slope_max_degrees,
    )
    product = _classification_product(thresholds)
    return FileResponse(
        path=product.preview_path,
        media_type="image/png",
        headers={"Content-Disposition": "inline"},
    )


@app.post("/api/route/plan", response_model=RoutePlanResponse)
def plan_terrain_route(request: RoutePlanRequest):
    """Find a slope-constrained grid route in the slope raster's projected CRS."""
    started_at = perf_counter()
    try:
        grid = get_cached_grid(SLOPE_FILE)
        route = plan_route(
            grid=grid,
            start_coordinate=(request.start.x, request.start.y),
            destination_coordinate=(request.destination.x, request.destination.y),
            max_slope_degrees=request.max_slope_degrees,
            slope_penalty=request.slope_penalty,
        )
    except RasterDataError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except PathPlanningError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(error), "feasible": False},
        ) from error

    terrain_profile = build_route_terrain_profile(
        grid,
        route.cells,
        ClassificationThresholds(
            low_max_degrees=request.low_slope_max_degrees,
            moderate_max_degrees=request.moderate_slope_max_degrees,
            high_max_degrees=request.high_slope_max_degrees,
        ),
    )
    return RoutePlanResponse(
        feasible=True,
        route_coordinates=[
            ProjectedCoordinate(x=x, y=y) for x, y in route.coordinates
        ],
        path_distance_m=route.distance_m,
        path_cell_count=len(route.cells),
        maximum_encountered_slope_degrees=route.max_slope_degrees,
        average_encountered_slope_degrees=route.average_slope_degrees,
        estimated_terrain_movement_cost=route.movement_cost,
        computation_time_ms=(perf_counter() - started_at) * 1000,
        coordinate_reference_system=grid.crs.to_wkt(),
        scientific_limitation=(
            "Slope-only planning over a provisional 200 m/pixel raster does not "
            "establish rover safety or physical traversability."
        ),
        terrain_profile=terrain_profile,
        provenance=route_provenance_references(PROVENANCE_FILE),
    )