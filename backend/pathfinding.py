"""A* route planning over the processed Jezero slope raster.

The planner treats each raster cell as a node. Slope is the only terrain cost
or traversal constraint; this does not model rover dynamics, obstacles, or
other physical traversability hazards.
"""

from __future__ import annotations

from dataclasses import dataclass
import heapq
import math
from pathlib import Path
import threading
from typing import TypeAlias

import numpy as np
import rasterio
from affine import Affine
from rasterio.crs import CRS


Coordinate: TypeAlias = tuple[float, float]
Cell: TypeAlias = tuple[int, int]

MAX_SEARCH_EXPANSIONS = 200_000
MAX_SLOPE_PENALTY = 100.0
DEFAULT_SLOPE_RASTER = (
    Path(__file__).resolve().parent / "data" / "processed" / "jezero_slope_deg.tif"
)


class PathPlanningError(ValueError):
    """Base class for invalid requests or routes that cannot be computed."""


class InvalidCoordinateError(PathPlanningError):
    """A projected coordinate does not map to a raster cell."""


class InvalidEndpointError(PathPlanningError):
    """A route endpoint is NoData or exceeds the requested slope limit."""


class NoRouteError(PathPlanningError):
    """No route connects the requested endpoints under the slope limit."""


class SearchLimitExceededError(PathPlanningError):
    """The search exceeded its fixed expansion budget."""


class RasterDataError(RuntimeError):
    """The raster is missing or does not meet the planner's requirements."""


@dataclass(frozen=True)
class TerrainGrid:
    slopes: np.ndarray
    valid: np.ndarray
    transform: Affine
    crs: CRS

    @property
    def height(self) -> int:
        return int(self.slopes.shape[0])

    @property
    def width(self) -> int:
        return int(self.slopes.shape[1])

    def cell_from_coordinate(self, coordinate: Coordinate) -> Cell:
        x, y = coordinate
        if not math.isfinite(x) or not math.isfinite(y):
            raise InvalidCoordinateError("Coordinates must be finite numbers.")

        inverse = ~self.transform
        column, row = inverse @ (x, y)
        if not math.isfinite(column) or not math.isfinite(row):
            raise InvalidCoordinateError("Coordinate could not be mapped to the raster.")

        cell = math.floor(row), math.floor(column)
        if not (0 <= cell[0] < self.height and 0 <= cell[1] < self.width):
            raise InvalidCoordinateError(
                "Coordinate is outside the processed Jezero raster bounds."
            )
        return cell

    def coordinate_for_cell(self, cell: Cell) -> Coordinate:
        row, column = cell
        x, y = self.transform @ (column + 0.5, row + 0.5)
        return float(x), float(y)

    def is_traversable(self, cell: Cell, max_slope_degrees: float) -> bool:
        row, column = cell
        return bool(
            self.valid[row, column]
            and self.slopes[row, column] <= max_slope_degrees
        )

    def distance_between(self, first: Cell, second: Cell) -> float:
        row_delta = second[0] - first[0]
        column_delta = second[1] - first[1]
        dx = self.transform.a * column_delta + self.transform.b * row_delta
        dy = self.transform.d * column_delta + self.transform.e * row_delta
        return math.hypot(dx, dy)


@dataclass(frozen=True)
class PlannedRoute:
    cells: tuple[Cell, ...]
    coordinates: tuple[Coordinate, ...]
    distance_m: float
    max_slope_degrees: float
    average_slope_degrees: float
    movement_cost: float


_cache_lock = threading.Lock()
_cached_grid: tuple[Path, int, int, TerrainGrid] | None = None


def _validate_projected_metre_crs(crs: CRS) -> None:
    if not crs.is_projected:
        raise RasterDataError("The slope raster CRS must be projected.")
    try:
        unit_name, conversion_factor = crs.linear_units_factor
    except (AttributeError, TypeError, ValueError) as error:
        raise RasterDataError(
            "The slope raster CRS does not define projected linear units."
        ) from error
    if unit_name.lower() not in {"metre", "meter"} or not math.isclose(
        conversion_factor, 1.0
    ):
        raise RasterDataError(
            "The slope raster's projected CRS must use metres for both axes."
        )


def _make_grid(
    slopes: np.ndarray,
    transform: Affine,
    crs: CRS,
    nodata: float | None = None,
) -> TerrainGrid:
    if slopes.ndim != 2 or not slopes.size:
        raise RasterDataError("The slope raster must be a non-empty single-band grid.")
    _validate_projected_metre_crs(crs)
    if not all(
        math.isfinite(value)
        for value in (transform.a, transform.b, transform.d, transform.e)
    ) or math.isclose(transform.determinant, 0.0):
        raise RasterDataError("The slope raster has an invalid affine transform.")

    valid = np.isfinite(slopes) & (slopes >= 0)
    if nodata is not None and math.isfinite(nodata):
        valid &= slopes != nodata
    slopes.setflags(write=False)
    valid.setflags(write=False)
    return TerrainGrid(slopes=slopes, valid=valid, transform=transform, crs=crs)


def get_cached_grid(
    path: Path = DEFAULT_SLOPE_RASTER,
) -> TerrainGrid:
    """Load one immutable raster grid and refresh the cache if its file changes."""
    global _cached_grid

    resolved_path = path.resolve()
    try:
        file_stat = resolved_path.stat()
    except OSError as error:
        raise RasterDataError(f"Slope raster is unavailable: {resolved_path}") from error

    with _cache_lock:
        if (
            _cached_grid is not None
            and _cached_grid[0] == resolved_path
            and _cached_grid[1] == file_stat.st_mtime_ns
            and _cached_grid[2] == file_stat.st_size
        ):
            return _cached_grid[3]

        try:
            with rasterio.open(resolved_path) as source:
                if source.count != 1:
                    raise RasterDataError(
                        "The slope raster must contain exactly one band."
                    )
                if source.crs is None:
                    raise RasterDataError("The slope raster has no coordinate reference system.")
                slopes = source.read(1)
                grid = _make_grid(
                    slopes=slopes,
                    transform=source.transform,
                    crs=source.crs,
                    nodata=source.nodata,
                )
        except RasterDataError:
            raise
        except (OSError, rasterio.errors.RasterioError) as error:
            raise RasterDataError(f"Unable to read slope raster: {error}") from error

        _cached_grid = (
            resolved_path,
            file_stat.st_mtime_ns,
            file_stat.st_size,
            grid,
        )
        return grid


def _heuristic(grid: TerrainGrid, cell: Cell, goal: Cell) -> float:
    # Edge costs are at least their projected Euclidean distance because the
    # slope multiplier is >= 1, so straight-line distance is admissible.
    return grid.distance_between(cell, goal)


def _movement_cost(
    grid: TerrainGrid,
    current: Cell,
    neighbor: Cell,
    max_slope_degrees: float,
    slope_penalty: float,
) -> float:
    distance = grid.distance_between(current, neighbor)
    mean_slope = (
        float(grid.slopes[current]) + float(grid.slopes[neighbor])
    ) / 2
    slope_ratio = mean_slope / max_slope_degrees
    return distance * (1 + slope_penalty * slope_ratio * slope_ratio)


def plan_route(
    grid: TerrainGrid,
    start_coordinate: Coordinate,
    destination_coordinate: Coordinate,
    max_slope_degrees: float,
    slope_penalty: float,
    max_expansions: int = MAX_SEARCH_EXPANSIONS,
) -> PlannedRoute:
    """Plan a least-cost 8-connected path using projected metre coordinates."""
    if not math.isfinite(max_slope_degrees) or not 0 < max_slope_degrees <= 90:
        raise PathPlanningError("Maximum slope must be greater than 0 and at most 90 degrees.")
    if not math.isfinite(slope_penalty) or not 0 <= slope_penalty <= MAX_SLOPE_PENALTY:
        raise PathPlanningError(
            f"Slope penalty must be between 0 and {MAX_SLOPE_PENALTY}."
        )
    if max_expansions < 1:
        raise PathPlanningError("Search expansion limit must be positive.")

    start = grid.cell_from_coordinate(start_coordinate)
    goal = grid.cell_from_coordinate(destination_coordinate)
    if not grid.is_traversable(start, max_slope_degrees):
        raise InvalidEndpointError(
            "Start cell is NoData or exceeds the maximum permitted slope."
        )
    if not grid.is_traversable(goal, max_slope_degrees):
        raise InvalidEndpointError(
            "Destination cell is NoData or exceeds the maximum permitted slope."
        )

    if start == goal:
        slope = float(grid.slopes[start])
        coordinate = grid.coordinate_for_cell(start)
        return PlannedRoute(
            cells=(start,),
            coordinates=(coordinate,),
            distance_m=0.0,
            max_slope_degrees=slope,
            average_slope_degrees=slope,
            movement_cost=0.0,
        )

    directions = (
        (-1, -1),
        (-1, 0),
        (-1, 1),
        (0, -1),
        (0, 1),
        (1, -1),
        (1, 0),
        (1, 1),
    )
    start_h = _heuristic(grid, start, goal)
    frontier: list[tuple[float, float, int, int, int, float]] = [
        (start_h, start_h, 0, start[0], start[1], 0.0)
    ]
    sequence = 0
    costs: dict[Cell, float] = {start: 0.0}
    parents: dict[Cell, Cell] = {}
    expansions = 0

    while frontier:
        _, _, _, row, column, queued_cost = heapq.heappop(frontier)
        current = (row, column)
        if queued_cost != costs.get(current):
            continue
        if current == goal:
            break
        if expansions >= max_expansions:
            raise SearchLimitExceededError(
                f"Route search exceeded its {max_expansions}-cell expansion limit."
            )
        expansions += 1

        for row_step, column_step in directions:
            neighbor = row + row_step, column + column_step
            next_row, next_column = neighbor
            if not (0 <= next_row < grid.height and 0 <= next_column < grid.width):
                continue
            if not grid.is_traversable(neighbor, max_slope_degrees):
                continue

            if row_step and column_step:
                side_a = row, next_column
                side_b = next_row, column
                if not (
                    grid.is_traversable(side_a, max_slope_degrees)
                    and grid.is_traversable(side_b, max_slope_degrees)
                ):
                    continue

            tentative_cost = costs[current] + _movement_cost(
                grid,
                current,
                neighbor,
                max_slope_degrees,
                slope_penalty,
            )
            if tentative_cost >= costs.get(neighbor, math.inf):
                continue

            costs[neighbor] = tentative_cost
            parents[neighbor] = current
            heuristic = _heuristic(grid, neighbor, goal)
            sequence += 1
            heapq.heappush(
                frontier,
                (
                    tentative_cost + heuristic,
                    heuristic,
                    sequence,
                    next_row,
                    next_column,
                    tentative_cost,
                ),
            )
    else:
        raise NoRouteError(
            "No route connects the endpoints without crossing NoData or exceeding the slope limit."
        )

    cells = [goal]
    while cells[-1] != start:
        parent = parents.get(cells[-1])
        if parent is None:
            raise NoRouteError("The route could not be reconstructed from the search result.")
        cells.append(parent)
        if len(cells) > max_expansions + 1:
            raise SearchLimitExceededError(
                "The route exceeds the configured maximum path length."
            )
    cells.reverse()

    distance = sum(
        grid.distance_between(first, second)
        for first, second in zip(cells, cells[1:])
    )
    path_slopes = [float(grid.slopes[cell]) for cell in cells]
    return PlannedRoute(
        cells=tuple(cells),
        coordinates=tuple(grid.coordinate_for_cell(cell) for cell in cells),
        distance_m=distance,
        max_slope_degrees=max(path_slopes),
        average_slope_degrees=sum(path_slopes) / len(path_slopes),
        movement_cost=costs[goal],
    )
