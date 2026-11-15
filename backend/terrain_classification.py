"""Slope-derived terrain classes and route-profile statistics."""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
import threading

import numpy as np
import rasterio
from PIL import Image

from backend.pathfinding import Cell, Coordinate, TerrainGrid

CLASS_NODATA = 0
CLASS_LOW = 1
CLASS_MODERATE = 2
CLASS_HIGH = 3
CLASS_ABOVE_DEFAULT = 4
CLASSIFICATION_COLORS = {
    CLASS_LOW: (45, 212, 191, 230),
    CLASS_MODERATE: (250, 204, 21, 230),
    CLASS_HIGH: (251, 146, 60, 235),
    CLASS_ABOVE_DEFAULT: (239, 68, 68, 245),
}
CLASSIFICATION_METHOD = (
    "Slope-only, project-defined categories; not rover-certified traversability."
)


class TerrainClassificationError(RuntimeError):
    """The source or derived terrain classification could not be used."""


@dataclass(frozen=True)
class ClassificationThresholds:
    low_max_degrees: float = 5.0
    moderate_max_degrees: float = 12.0
    high_max_degrees: float = 18.0

    def __post_init__(self) -> None:
        values = (
            self.low_max_degrees,
            self.moderate_max_degrees,
            self.high_max_degrees,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Classification thresholds must be finite.")
        if not (
            0 <= self.low_max_degrees
            < self.moderate_max_degrees
            < self.high_max_degrees
            <= 90
        ):
            raise ValueError(
                "Thresholds must satisfy 0 <= low < moderate < high <= 90 degrees."
            )

    def path_token(self) -> str:
        return "_".join(
            _number_token(value)
            for value in (
                self.low_max_degrees,
                self.moderate_max_degrees,
                self.high_max_degrees,
            )
        )


@dataclass(frozen=True)
class ClassificationProduct:
    raster_path: Path
    preview_path: Path
    width: int
    height: int
    crs: str
    transform: tuple[float, ...]
    resolution: tuple[float, float]
    valid_cell_count: int
    nodata_cell_count: int
    category_counts: dict[int, int]
    thresholds: ClassificationThresholds


@dataclass(frozen=True)
class HighSlopeSegment:
    start_route_cell_index: int
    end_route_cell_index: int
    cell_count: int
    distance_m: float
    maximum_slope_degrees: float
    start_coordinate: Coordinate
    end_coordinate: Coordinate

    def as_dict(self) -> dict[str, int | float | Coordinate]:
        return {
            "start_route_cell_index": self.start_route_cell_index,
            "end_route_cell_index": self.end_route_cell_index,
            "cell_count": self.cell_count,
            "distance_m": self.distance_m,
            "maximum_slope_degrees": self.maximum_slope_degrees,
            "start_coordinate": self.start_coordinate,
            "end_coordinate": self.end_coordinate,
        }


_generation_lock = threading.Lock()


def _number_token(value: float) -> str:
    return format(value, "g").replace("-", "m").replace(".", "p")


def category_for_slope(
    slope_degrees: float,
    thresholds: ClassificationThresholds = ClassificationThresholds(),
) -> int:
    if not math.isfinite(slope_degrees) or slope_degrees < 0:
        return CLASS_NODATA
    if slope_degrees <= thresholds.low_max_degrees:
        return CLASS_LOW
    if slope_degrees <= thresholds.moderate_max_degrees:
        return CLASS_MODERATE
    if slope_degrees <= thresholds.high_max_degrees:
        return CLASS_HIGH
    return CLASS_ABOVE_DEFAULT


def classify_slope_array(
    slopes: np.ndarray,
    nodata: float | None = None,
    thresholds: ClassificationThresholds = ClassificationThresholds(),
) -> np.ndarray:
    """Return uint8 class codes; 0 marks NoData and 1–4 are slope classes."""
    valid = np.isfinite(slopes) & (slopes >= 0)
    if nodata is not None and math.isfinite(nodata):
        valid &= slopes != nodata

    classified = np.zeros(slopes.shape, dtype=np.uint8)
    classified[valid & (slopes <= thresholds.low_max_degrees)] = CLASS_LOW
    classified[
        valid
        & (slopes > thresholds.low_max_degrees)
        & (slopes <= thresholds.moderate_max_degrees)
    ] = CLASS_MODERATE
    classified[
        valid
        & (slopes > thresholds.moderate_max_degrees)
        & (slopes <= thresholds.high_max_degrees)
    ] = CLASS_HIGH
    classified[valid & (slopes > thresholds.high_max_degrees)] = CLASS_ABOVE_DEFAULT
    return classified


def _product_paths(
    output_dir: Path,
    thresholds: ClassificationThresholds,
) -> tuple[Path, Path]:
    stem = f"jezero_traversability_{thresholds.path_token()}"
    return output_dir / f"{stem}.tif", output_dir / f"{stem}_preview.png"


def ensure_classification_product(
    slope_path: Path,
    output_dir: Path,
    thresholds: ClassificationThresholds = ClassificationThresholds(),
) -> ClassificationProduct:
    """Create/update a compact classified GeoTIFF and matching RGBA preview."""
    output_dir.mkdir(parents=True, exist_ok=True)
    raster_path, preview_path = _product_paths(output_dir, thresholds)
    try:
        source_stat = slope_path.stat()
    except OSError as error:
        raise TerrainClassificationError(
            f"Slope raster is unavailable: {slope_path}"
        ) from error

    with _generation_lock:
        if not _classification_is_current(raster_path, source_stat, thresholds):
            _write_classification(
                slope_path,
                raster_path,
                source_stat,
                thresholds,
            )
        if (
            not preview_path.exists()
            or preview_path.stat().st_mtime_ns < raster_path.stat().st_mtime_ns
        ):
            _write_preview(raster_path, preview_path)
        return _read_product(raster_path, preview_path, thresholds)


def _classification_is_current(
    raster_path: Path,
    source_stat: os.stat_result,
    thresholds: ClassificationThresholds,
) -> bool:
    if not raster_path.exists():
        return False
    try:
        with rasterio.open(raster_path) as classified:
            tags = classified.tags()
            return (
                classified.count == 1
                and classified.dtypes[0] == "uint8"
                and classified.nodata == CLASS_NODATA
                and tags.get("source_mtime_ns") == str(source_stat.st_mtime_ns)
                and tags.get("source_size") == str(source_stat.st_size)
                and tags.get("low_max_degrees") == str(thresholds.low_max_degrees)
                and tags.get("moderate_max_degrees")
                == str(thresholds.moderate_max_degrees)
                and tags.get("high_max_degrees") == str(thresholds.high_max_degrees)
            )
    except (OSError, rasterio.errors.RasterioError):
        return False


def _write_classification(
    slope_path: Path,
    raster_path: Path,
    source_stat: os.stat_result,
    thresholds: ClassificationThresholds,
) -> None:
    temporary_path = raster_path.with_name(
        f"{raster_path.name}.{os.getpid()}.tmp"
    )
    try:
        with rasterio.open(slope_path) as source:
            if source.count != 1 or source.crs is None:
                raise TerrainClassificationError(
                    "The source slope raster must be single-band and georeferenced."
                )
            profile = source.profile.copy()
            profile.update(
                driver="GTiff",
                dtype="uint8",
                count=1,
                nodata=CLASS_NODATA,
                compress="deflate",
                predictor=2,
            )
            counts = {code: 0 for code in CLASSIFICATION_COLORS}
            valid_count = 0
            with rasterio.open(temporary_path, "w", **profile) as output:
                output.set_band_description(1, "Project-defined slope class")
                output.update_tags(
                    classification_method=CLASSIFICATION_METHOD,
                    class_nodata=CLASS_NODATA,
                    low_max_degrees=thresholds.low_max_degrees,
                    moderate_max_degrees=thresholds.moderate_max_degrees,
                    high_max_degrees=thresholds.high_max_degrees,
                    class_1="Low slope",
                    class_2="Moderate slope",
                    class_3="High slope",
                    class_4="Exceeds default slope constraint",
                    source_file=slope_path.name,
                    source_mtime_ns=source_stat.st_mtime_ns,
                    source_size=source_stat.st_size,
                )
                for _, window in source.block_windows(1):
                    slopes = source.read(1, window=window)
                    classes = classify_slope_array(
                        slopes,
                        source.nodata,
                        thresholds,
                    )
                    output.write(classes, 1, window=window)
                    valid_count += int(np.count_nonzero(classes))
                    block_counts = np.bincount(classes.ravel(), minlength=5)
                    for code in counts:
                        counts[code] += int(block_counts[code])

                output.update_tags(
                    valid_cell_count=valid_count,
                    nodata_cell_count=source.width * source.height - valid_count,
                    count_low=counts[CLASS_LOW],
                    count_moderate=counts[CLASS_MODERATE],
                    count_high=counts[CLASS_HIGH],
                    count_exceeds_default=counts[CLASS_ABOVE_DEFAULT],
                )
        os.replace(temporary_path, raster_path)
    except (OSError, rasterio.errors.RasterioError) as error:
        temporary_path.unlink(missing_ok=True)
        raise TerrainClassificationError(
            f"Unable to generate traversability raster: {error}"
        ) from error
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _write_preview(raster_path: Path, preview_path: Path) -> None:
    temporary_path = preview_path.with_name(
        f"{preview_path.name}.{os.getpid()}.tmp"
    )
    try:
        with rasterio.open(raster_path) as classified:
            classes = classified.read(1)
        rgba = np.zeros((*classes.shape, 4), dtype=np.uint8)
        for code, color in CLASSIFICATION_COLORS.items():
            rgba[classes == code] = color
        Image.fromarray(rgba, mode="RGBA").save(temporary_path, format="PNG")
        os.replace(temporary_path, preview_path)
    except (OSError, rasterio.errors.RasterioError) as error:
        temporary_path.unlink(missing_ok=True)
        raise TerrainClassificationError(
            f"Unable to generate traversability preview: {error}"
        ) from error
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _read_product(
    raster_path: Path,
    preview_path: Path,
    thresholds: ClassificationThresholds,
) -> ClassificationProduct:
    try:
        with rasterio.open(raster_path) as raster:
            tags = raster.tags()
            valid_count = int(tags["valid_cell_count"])
            counts = {
                CLASS_LOW: int(tags["count_low"]),
                CLASS_MODERATE: int(tags["count_moderate"]),
                CLASS_HIGH: int(tags["count_high"]),
                CLASS_ABOVE_DEFAULT: int(tags["count_exceeds_default"]),
            }
            return ClassificationProduct(
                raster_path=raster_path,
                preview_path=preview_path,
                width=raster.width,
                height=raster.height,
                crs=raster.crs.to_string() if raster.crs else "",
                transform=tuple(raster.transform),
                resolution=raster.res,
                valid_cell_count=valid_count,
                nodata_cell_count=int(tags["nodata_cell_count"]),
                category_counts=counts,
                thresholds=thresholds,
            )
    except (OSError, KeyError, ValueError, rasterio.errors.RasterioError) as error:
        raise TerrainClassificationError(
            f"Unable to read traversability product metadata: {error}"
        ) from error


def build_route_terrain_profile(
    grid: TerrainGrid,
    cells: tuple[Cell, ...],
    thresholds: ClassificationThresholds = ClassificationThresholds(),
) -> dict[str, object]:
    """Summarize actual route-cell slopes and distance by project class.

    Each route edge's distance is attributed to the more severe class at its
    two endpoint cells. This conservative convention is also reflected in the
    API's analysis metadata.
    """
    if not cells:
        raise ValueError("Cannot profile an empty route.")

    slopes = [float(grid.slopes[cell]) for cell in cells]
    classes = [category_for_slope(slope, thresholds) for slope in slopes]
    class_metadata = category_definitions(thresholds)
    class_counts = {code: 0 for code in CLASSIFICATION_COLORS}
    for code in classes:
        class_counts[code] += 1

    class_distances = {code: 0.0 for code in CLASSIFICATION_COLORS}
    for first, second, first_class, second_class in zip(
        cells,
        cells[1:],
        classes,
        classes[1:],
    ):
        edge_class = max(first_class, second_class)
        class_distances[edge_class] += grid.distance_between(first, second)

    segments: list[HighSlopeSegment] = []
    segment_start: int | None = None
    for index, code in enumerate(classes + [CLASS_LOW]):
        if code >= CLASS_HIGH and segment_start is None:
            segment_start = index
        elif code < CLASS_HIGH and segment_start is not None:
            segment_end = index - 1
            segment_cells = cells[segment_start : segment_end + 1]
            segments.append(
                HighSlopeSegment(
                    start_route_cell_index=segment_start,
                    end_route_cell_index=segment_end,
                    cell_count=len(segment_cells),
                    distance_m=sum(
                        grid.distance_between(first, second)
                        for first, second in zip(
                            segment_cells,
                            segment_cells[1:],
                        )
                    ),
                    maximum_slope_degrees=max(slopes[segment_start : segment_end + 1]),
                    start_coordinate=grid.coordinate_for_cell(segment_cells[0]),
                    end_coordinate=grid.coordinate_for_cell(segment_cells[-1]),
                )
            )
            segment_start = None

    highest_slope_segment = None
    high_route_indices = [
        index for index, code in enumerate(classes) if code >= CLASS_HIGH
    ]
    if high_route_indices:
        highest_slope_index = max(
            high_route_indices,
            key=lambda index: slopes[index],
        )
        highest_slope_segment = next(
            segment
            for segment in segments
            if segment.start_route_cell_index
            <= highest_slope_index
            <= segment.end_route_cell_index
        ).as_dict()

    total_cells = len(cells)
    category_stats = []
    for category in class_metadata:
        code = category["code"]
        count = class_counts[code]
        category_stats.append(
            {
                **category,
                "cell_count": count,
                "percentage_of_route_cells": count / total_cells * 100,
                "distance_m": class_distances[code],
            }
        )

    return {
        "thresholds": {
            "low_max_degrees": thresholds.low_max_degrees,
            "moderate_max_degrees": thresholds.moderate_max_degrees,
            "high_max_degrees": thresholds.high_max_degrees,
        },
        "slope_distribution_degrees": {
            "minimum": min(slopes),
            "average": sum(slopes) / total_cells,
            "maximum": max(slopes),
        },
        "categories": category_stats,
        "high_slope_segment_count": len(segments),
        "consecutive_high_slope_segments": [
            segment.as_dict() for segment in segments
        ],
        "highest_slope_segment": highest_slope_segment,
        "analysis_metadata": {
            "source": "Actual source slope values at calculated route cells",
            "category_method": CLASSIFICATION_METHOD,
            "edge_distance_assignment": (
                "Each edge is attributed to the more severe class of its endpoint cells."
            ),
        },
    }


def category_definitions(
    thresholds: ClassificationThresholds = ClassificationThresholds(),
) -> list[dict[str, int | float | str]]:
    return [
        {
            "code": CLASS_LOW,
            "name": "Low slope",
            "minimum_exclusive_degrees": None,
            "maximum_inclusive_degrees": thresholds.low_max_degrees,
            "color": "#2dd4bf",
        },
        {
            "code": CLASS_MODERATE,
            "name": "Moderate slope",
            "minimum_exclusive_degrees": thresholds.low_max_degrees,
            "maximum_inclusive_degrees": thresholds.moderate_max_degrees,
            "color": "#facc15",
        },
        {
            "code": CLASS_HIGH,
            "name": "High slope",
            "minimum_exclusive_degrees": thresholds.moderate_max_degrees,
            "maximum_inclusive_degrees": thresholds.high_max_degrees,
            "color": "#fb923c",
        },
        {
            "code": CLASS_ABOVE_DEFAULT,
            "name": "Exceeds default slope constraint",
            "minimum_exclusive_degrees": thresholds.high_max_degrees,
            "maximum_inclusive_degrees": None,
            "color": "#ef4444",
        },
    ]
