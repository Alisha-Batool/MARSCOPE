import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from rasterio.crs import CRS

from backend.pathfinding import _make_grid
from backend.terrain_classification import (
    CLASS_ABOVE_DEFAULT,
    CLASS_HIGH,
    CLASS_LOW,
    CLASS_MODERATE,
    CLASS_NODATA,
    ClassificationThresholds,
    TerrainClassificationError,
    build_route_terrain_profile,
    classify_slope_array,
    ensure_classification_product,
)


class TerrainClassificationTests(unittest.TestCase):
    def test_classification_boundaries_and_nodata(self):
        slopes = np.array(
            [[0, 5, 5.01, 12, 12.01, 18, 18.01, np.nan, -9999, -1]],
            dtype=np.float32,
        )

        classes = classify_slope_array(slopes, nodata=-9999)

        np.testing.assert_array_equal(
            classes,
            [[
                CLASS_LOW,
                CLASS_LOW,
                CLASS_MODERATE,
                CLASS_MODERATE,
                CLASS_HIGH,
                CLASS_HIGH,
                CLASS_ABOVE_DEFAULT,
                CLASS_NODATA,
                CLASS_NODATA,
                CLASS_NODATA,
            ]],
        )
        self.assertEqual(classes.dtype, np.uint8)

    def test_configurable_thresholds(self):
        thresholds = ClassificationThresholds(4, 10, 15)
        slopes = np.array([[4, 4.1, 10, 10.1, 15, 15.1]], dtype=np.float32)

        classes = classify_slope_array(slopes, thresholds=thresholds)

        np.testing.assert_array_equal(classes, [[1, 2, 2, 3, 3, 4]])
        with self.assertRaises(ValueError):
            ClassificationThresholds(12, 5, 18)

    def test_missing_source_raster_reports_classification_error(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            with self.assertRaises(TerrainClassificationError):
                ensure_classification_product(
                    temporary_path / "missing_slope.tif",
                    temporary_path / "processed",
                )

    def test_generated_raster_preserves_georeferencing_and_counts(self):
        transform = Affine(200, 0, -85084.5, 0, -200, 89432.5)
        crs = CRS.from_proj4(
            "+proj=stere +lat_0=18.4 +lon_0=77.4 +R=3396190 +units=m +no_defs"
        )
        source_values = np.array(
            [[0, 5.01, 12.01], [18.01, -9999, np.nan]],
            dtype=np.float32,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            source_path = temporary_path / "source_slope.tif"
            with rasterio.open(
                source_path,
                "w",
                driver="GTiff",
                width=3,
                height=2,
                count=1,
                dtype="float32",
                crs=crs,
                transform=transform,
                nodata=-9999,
            ) as source:
                source.write(source_values, 1)

            product = ensure_classification_product(
                source_path,
                temporary_path / "processed",
            )
            with rasterio.open(product.raster_path) as classified:
                result = classified.read(1)
                self.assertEqual(classified.width, 3)
                self.assertEqual(classified.height, 2)
                self.assertEqual(classified.crs, crs)
                self.assertEqual(classified.transform, transform)
                self.assertEqual(classified.res, (200, 200))
                self.assertEqual(classified.dtypes[0], "uint8")
                self.assertEqual(classified.nodata, CLASS_NODATA)
                np.testing.assert_array_equal(
                    result,
                    [[1, 2, 3], [4, 0, 0]],
                )
            self.assertEqual(product.valid_cell_count, 4)
            self.assertEqual(product.nodata_cell_count, 2)
            self.assertEqual(product.category_counts, {1: 1, 2: 1, 3: 1, 4: 1})
            self.assertTrue(product.preview_path.exists())

    def test_route_profile_counts_segments_and_category_distances(self):
        transform = Affine(100, 0, 0, 0, -100, 100)
        slopes = np.array([[2, 6, 13, 19, 15, 4]], dtype=np.float32)
        grid = _make_grid(
            slopes=slopes,
            transform=transform,
            crs=CRS.from_epsg(3857),
        )
        cells = tuple((0, column) for column in range(6))

        profile = build_route_terrain_profile(grid, cells)

        categories = {entry["code"]: entry for entry in profile["categories"]}
        self.assertEqual(
            [categories[code]["cell_count"] for code in (1, 2, 3, 4)],
            [2, 1, 2, 1],
        )
        self.assertEqual(
            sum(categories[code]["distance_m"] for code in categories),
            500,
        )
        self.assertEqual(profile["high_slope_segment_count"], 1)
        segment = profile["consecutive_high_slope_segments"][0]
        self.assertEqual(segment["start_route_cell_index"], 2)
        self.assertEqual(segment["end_route_cell_index"], 4)
        self.assertEqual(segment["cell_count"], 3)
        self.assertEqual(segment["distance_m"], 200)
        self.assertEqual(
            profile["highest_slope_segment"]["maximum_slope_degrees"],
            19,
        )


if __name__ == "__main__":
    unittest.main()
