import math
import unittest

import numpy as np
from affine import Affine
from rasterio.crs import CRS

from backend.pathfinding import (
    InvalidCoordinateError,
    InvalidEndpointError,
    NoRouteError,
    _make_grid,
    plan_route,
)


TRANSFORM = Affine(200, 0, 1000, 0, -200, 2000)
CRS_METRES = CRS.from_epsg(3857)


def make_grid(values: list[list[float]]):
    return _make_grid(
        slopes=np.array(values, dtype=np.float32),
        transform=TRANSFORM,
        crs=CRS_METRES,
        nodata=-9999,
    )


def center(row: int, column: int) -> tuple[float, float]:
    x, y = TRANSFORM @ (column + 0.5, row + 0.5)
    return float(x), float(y)


class PathfindingTests(unittest.TestCase):
    def test_finds_route_and_returns_cell_center_coordinates(self):
        grid = make_grid([[0, 0], [0, 0]])
        route = plan_route(grid, center(0, 0), center(1, 1), 10, 2)

        self.assertEqual(route.cells, ((0, 0), (1, 1)))
        self.assertAlmostEqual(route.distance_m, 200 * math.sqrt(2))
        self.assertAlmostEqual(route.movement_cost, route.distance_m)
        for coordinate, cell in zip(route.coordinates, route.cells):
            self.assertEqual(grid.cell_from_coordinate(coordinate), cell)

    def test_rejects_blocked_destination(self):
        grid = make_grid([[0, 20], [0, 0]])

        with self.assertRaises(InvalidEndpointError):
            plan_route(grid, center(0, 0), center(0, 1), 10, 1)

    def test_rejects_out_of_raster_coordinate(self):
        grid = make_grid([[0, 0], [0, 0]])

        with self.assertRaises(InvalidCoordinateError):
            plan_route(grid, (900, 2000), center(1, 1), 10, 1)

    def test_reports_unreachable_destination(self):
        grid = make_grid([[0, -9999, 0]])

        with self.assertRaises(NoRouteError):
            plan_route(grid, center(0, 0), center(0, 2), 10, 1)

    def test_prevents_diagonal_corner_cutting(self):
        grid = make_grid([[0, 20], [20, 0]])

        with self.assertRaises(NoRouteError):
            plan_route(grid, center(0, 0), center(1, 1), 10, 1)

    def test_slope_penalty_prefers_a_flatter_detour(self):
        grid = make_grid(
            [
                [0, 0, 0],
                [0, 9, 0],
                [0, 0, 0],
            ]
        )
        direct = plan_route(grid, center(1, 0), center(1, 2), 10, 0)
        penalized = plan_route(grid, center(1, 0), center(1, 2), 10, 100)

        self.assertIn((1, 1), direct.cells)
        self.assertNotIn((1, 1), penalized.cells)
        self.assertGreater(penalized.movement_cost, direct.movement_cost)

    def test_rejects_start_cell_above_slope_limit(self):
        grid = make_grid([[20, 0], [0, 0]])

        with self.assertRaises(InvalidEndpointError):
            plan_route(grid, center(0, 0), center(1, 1), 10, 1)


if __name__ == "__main__":
    unittest.main()
