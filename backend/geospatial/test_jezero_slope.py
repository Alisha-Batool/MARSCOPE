import json
from pathlib import Path
import numpy as np
import rasterio

from rasterio.windows import from_bounds
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.transform import array_bounds

SOURCE = (
    r"C:\Users\MIAN ZAIN\Downloads"
    r"\Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif"
)

# Approximate Jezero region
WEST, SOUTH, EAST, NORTH = 75.9, 16.9, 78.9, 19.9

# Local Mars stereographic projection
MARS_LOCAL = (
    "+proj=stere +lat_0=18.4 +lon_0=77.4 "
    "+k=1 +x_0=0 +y_0=0 "
    "+R=3396190 +units=m +no_defs"
)

with rasterio.open(SOURCE) as src:

    print("Reading Jezero region...")

    window = from_bounds(
        WEST, SOUTH, EAST, NORTH,
        transform=src.transform
    ).round_offsets().round_lengths()

    elevation = src.read(
        1,
        window=window,
        masked=True
    ).astype("float32")

    source_transform = src.window_transform(window)

    print("Source shape:", elevation.shape)
    print("Source CRS:", src.crs)

    # Obtain geographic bounds of the extracted window
    bounds = array_bounds(
        elevation.shape[0],
        elevation.shape[1],
        source_transform
    )

    print("Reprojecting into local Mars coordinates...")

    dst_transform, dst_width, dst_height = calculate_default_transform(
        src.crs,
        MARS_LOCAL,
        elevation.shape[1],
        elevation.shape[0],
        *bounds,
        resolution=200
    )

    destination = np.full(
        (dst_height, dst_width),
        np.nan,
        dtype=np.float32
    )

    reproject(
        source=elevation.filled(np.nan),
        destination=destination,
        src_transform=source_transform,
        src_crs=src.crs,
        src_nodata=np.nan,
        dst_transform=dst_transform,
        dst_crs=MARS_LOCAL,
        dst_nodata=np.nan,
        resampling=Resampling.bilinear
    )

    print("Projected shape:", destination.shape)
    print("Projected pixel size:", dst_transform.a, dst_transform.e)

    # Elevation values are interpreted as metres only after
    # confirming the source product's elevation convention.
    valid = np.isfinite(destination)

    # Avoid calculating gradients across NoData cells.
    safe = np.where(valid, destination, 0.0)

    dy, dx = np.gradient(
        safe,
        200.0,
        200.0
    )

    slope = np.degrees(
        np.arctan(np.sqrt(dx**2 + dy**2))
    )

    # Exclude cells adjacent to NoData to avoid artificial edges.
    from scipy.ndimage import binary_erosion

    interior = binary_erosion(valid, iterations=1)

    valid_slope = slope[interior]

    if valid_slope.size == 0:
        raise RuntimeError("No valid slope cells available.")

    print("\n===== JEZERO SLOPE ANALYSIS =====")
    print("Valid slope pixels:", valid_slope.size)
    print("Minimum slope:", float(valid_slope.min()))
    print("Maximum slope:", float(valid_slope.max()))
    print("Mean slope:", float(valid_slope.mean()))
    print("Median slope:", float(np.median(valid_slope)))
    print("95th percentile:", float(np.percentile(valid_slope, 95)))

    threshold = 18.0

    safe_percentage = (
        np.count_nonzero(valid_slope <= threshold)
        / valid_slope.size
    ) * 100

    hazardous_percentage = 100 - safe_percentage

    print("Slope threshold:", threshold, "degrees")
    print("Terrain at/below threshold:", round(safe_percentage, 2), "%")
    print("Terrain above threshold:", round(hazardous_percentage, 2), "%")
    # Persist analysis outputs
    output_dir = Path("backend/data/processed")
    output_dir.mkdir(parents=True, exist_ok=True)

    slope_path = output_dir / "jezero_slope_deg.tif"
    summary_path = output_dir / "jezero_terrain_summary.json"

    # Exclude invalid boundaries from the output raster
    nodata_value = -9999.0
    slope_output = np.where(
        interior,
        slope,
        nodata_value
    ).astype(np.float32)

    profile = {
        "driver": "GTiff",
        "height": dst_height,
        "width": dst_width,
        "count": 1,
        "dtype": "float32",
        "crs": MARS_LOCAL,
        "transform": dst_transform,
        "nodata": nodata_value,
        "compress": "deflate",
        "predictor": 3,
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
    }

    with rasterio.open(slope_path, "w", **profile) as dst:
        dst.write(slope_output, 1)
        dst.set_band_description(1, "Slope in degrees")

    summary = {
        "region": "Jezero Crater",
        "source": "USGS Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2",
        "source_resolution_m": 200,
        "analysis_status": "provisional",
        "vertical_units_verified": False,
        "slope_method": "central_difference",
        "slope_threshold_degrees": threshold,
        "valid_pixels": int(valid_slope.size),
        "minimum_slope_degrees": float(valid_slope.min()),
        "maximum_slope_degrees": float(valid_slope.max()),
        "mean_slope_degrees": float(valid_slope.mean()),
        "median_slope_degrees": float(np.median(valid_slope)),
        "percentile_95_slope_degrees": float(
            np.percentile(valid_slope, 95)
        ),
        "terrain_at_or_below_threshold_percent": float(
            safe_percentage
        ),
        "terrain_above_threshold_percent": float(
            hazardous_percentage
        ),
        "slope_raster": "jezero_slope_deg.tif",
    }

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=4)

    print("\nSaved slope raster:", slope_path)
    print("Saved terrain summary:", summary_path)
    print("\nAnalysis complete.")
