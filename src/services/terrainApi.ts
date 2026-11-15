const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export type ApiHealth = {
  status: string;
  data_status: string;
  message: string;
};

export type TerrainSummary = {
  region: string;
  source: string;
  source_resolution_m: number;
  analysis_status: string;
  vertical_units_verified: boolean;
  slope_method: string;
  valid_pixels: number;
  minimum_slope_degrees: number;
  maximum_slope_degrees: number;
  mean_slope_degrees: number;
  median_slope_degrees: number;
  percentile_95_slope_degrees: number;
  terrain_at_or_below_threshold_percent: number;
  terrain_above_threshold_percent: number;
};

export type SlopeMetadata = {
  region: string;
  width: number;
  height: number;
  resolution: { x: number; y: number; unit: string };
  crs: string;
  bounds: { left: number; bottom: number; right: number; top: number };
  nodata: number | null;
  band_description: string | null;
  raster_url: string;
};

export const slopePreviewUrl =
  `${API_BASE}/api/terrain/jezero/slope/preview`;

export async function fetchApi<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { signal });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body: unknown = await response.json();
      if (
        typeof body === "object" &&
        body !== null &&
        "detail" in body &&
        typeof body.detail === "string"
      ) {
        detail = body.detail;
      }
    } catch {
      detail = response.statusText || "Response body was not valid JSON";
    }
    throw new Error(`${path}: ${detail || `HTTP ${response.status}`}`);
  }
  return response.json() as Promise<T>;
}
