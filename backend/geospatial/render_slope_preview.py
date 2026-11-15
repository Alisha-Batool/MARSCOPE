from pathlib import Path

import numpy as np
import rasterio
from PIL import Image

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data" / "processed"

INPUT_FILE = DATA_DIR / "jezero_slope_deg.tif"
OUTPUT_FILE = DATA_DIR / "jezero_slope_preview.png"

if not INPUT_FILE.exists():
    raise FileNotFoundError(f"Slope raster not found: {INPUT_FILE}")

with rasterio.open(INPUT_FILE) as src:
    slope = src.read(1, masked=True).astype(np.float32)
    valid = ~np.ma.getmaskarray(slope)
    values = slope.filled(0)

    if not np.any(valid):
        raise ValueError("Slope raster contains no valid pixels.")

    # Slope categories in degrees.
    colors = np.zeros((*values.shape, 4), dtype=np.uint8)

    colors[valid & (values <= 5)] = [45, 212, 191, 220]    # 0–5°
    colors[valid & (values > 5) & (values <= 12)] = [250, 204, 21, 220]
    colors[valid & (values > 12) & (values <= 18)] = [251, 146, 60, 220]
    colors[valid & (values > 18)] = [239, 68, 68, 235]

    image = Image.fromarray(colors, mode="RGBA")
    image.save(OUTPUT_FILE)

    print("Slope preview generated successfully.")
    print(f"Input:  {INPUT_FILE}")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Dimensions: {src.width} x {src.height}")
    print(f"Valid pixels: {np.count_nonzero(valid):,}")
    print(f"Minimum slope: {values[valid].min():.2f}°")
    print(f"Maximum slope: {values[valid].max():.2f}°")
    print(f"PNG size: {OUTPUT_FILE.stat().st_size:,} bytes")
