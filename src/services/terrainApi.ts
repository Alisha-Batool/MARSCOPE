const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";
const API_REQUEST_TIMEOUT_MS = 15_000;

function createRequestSignal(externalSignal?: AbortSignal) {
  const controller = new AbortController();
  const timeout = setTimeout(
    () =>
      controller.abort(
        new DOMException(
          `The request timed out after ${API_REQUEST_TIMEOUT_MS} ms.`,
          "TimeoutError",
        ),
      ),
    API_REQUEST_TIMEOUT_MS,
  );
  const relayAbort = () => controller.abort(externalSignal?.reason);
  if (externalSignal?.aborted) {
    relayAbort();
  } else {
    externalSignal?.addEventListener("abort", relayAbort, { once: true });
  }

  return {
    signal: controller.signal,
    timedOut: () =>
      controller.signal.reason instanceof DOMException &&
      controller.signal.reason.name === "TimeoutError",
    dispose: () => {
      clearTimeout(timeout);
      externalSignal?.removeEventListener("abort", relayAbort);
    },
  };
}

export type ApiHealth = {
  status: string;
  data_status: string;
  route_planning_available?: boolean;
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
  provenance?: ProvenanceReferences;
};

export type ProvenanceReferences = {
  status: string;
  manifest_id: string;
  source_dataset_record_id?: string;
  slope_product?: string;
  classification_product?: string;
  route_algorithm?: string;
  checksum_verification?: string;
  reason?: string;
};

export type ProvenanceProductStatus = {
  record_id: string;
  filename: string;
  available: boolean;
  verification_status: string;
  checksum_status: string;
  metadata_status: string;
  expected_sha256: string | null;
  actual_sha256: string | null;
  size_bytes: number | null;
};

export type ProvenanceManifest = {
  manifest_id: string;
  analysis_status: string;
  source_dataset: {
    record_id: string;
    dataset_title: string;
    version: string;
    provider: string;
    publisher: string;
    product_identifier: string;
    product_url: string;
    publication_date: string;
    recommended_citation: string;
    nominal_product_resolution: { value: number; unit: string };
    original_asset: {
      filename: string;
      availability_at_capture: string;
      raster_metadata: {
        width: number;
        height: number;
        data_types: string[];
        nodata: number | null;
      };
      checksum: { sha256: string | null; status: string; reason?: string };
    };
  };
  processing_pipeline: Array<{
    stage_id: string;
    operation: string;
    mathematical_method?: string;
    movement_cost_formula?: string;
    known_limitations: string[];
  }>;
  derived_products: Array<{
    record_id: string;
    filename: string;
    product_type: string;
    generated_at: { value: string; evidence: string };
    checksum: { sha256: string };
  }>;
  scientific_limitations: string[];
  ai_assisted_development_disclosure: string;
};

export type ProvenanceReport = {
  manifest: ProvenanceManifest;
  manifest_status: string;
  source_asset_status: {
    filename: string;
    availability: string;
    checksum_status: string;
  };
  product_verification: ProvenanceProductStatus[];
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

export type ProjectedCoordinate = {
  x: number;
  y: number;
};

export type RoutePlanRequest = {
  start: ProjectedCoordinate;
  destination: ProjectedCoordinate;
  max_slope_degrees: number;
  slope_penalty: number;
  low_slope_max_degrees?: number;
  moderate_slope_max_degrees?: number;
  high_slope_max_degrees?: number;
};

export type TraversabilityCategory = {
  code: number;
  name: string;
  minimum_exclusive_degrees: number | null;
  maximum_inclusive_degrees: number | null;
  color: string;
  cell_count: number;
  percentage_of_valid_cells: number;
};

export type TraversabilitySummary = {
  width: number;
  height: number;
  crs: string;
  resolution: { x: number; y: number; unit: string };
  transform: number[];
  category_definitions: TraversabilityCategory[];
  valid_cell_count: number;
  nodata_cell_count: number;
  analysis_metadata: Record<string, unknown>;
  raster_url: string;
  preview_url: string;
};

export type RouteProfileCategory = Omit<
  TraversabilityCategory,
  "percentage_of_valid_cells"
> & {
  percentage_of_route_cells: number;
  distance_m: number;
};

export type RouteSlopeSegment = {
  start_route_cell_index: number;
  end_route_cell_index: number;
  cell_count: number;
  distance_m: number;
  maximum_slope_degrees: number;
  start_coordinate: [number, number];
  end_coordinate: [number, number];
};

export type RouteTerrainProfile = {
  thresholds: {
    low_max_degrees: number;
    moderate_max_degrees: number;
    high_max_degrees: number;
  };
  slope_distribution_degrees: {
    minimum: number;
    average: number;
    maximum: number;
  };
  categories: RouteProfileCategory[];
  high_slope_segment_count: number;
  consecutive_high_slope_segments: RouteSlopeSegment[];
  highest_slope_segment: RouteSlopeSegment | null;
  analysis_metadata: Record<string, string>;
};

export type RoutePlanResponse = {
  feasible: boolean;
  route_coordinates: ProjectedCoordinate[];
  path_distance_m: number;
  path_cell_count: number;
  maximum_encountered_slope_degrees: number;
  average_encountered_slope_degrees: number;
  estimated_terrain_movement_cost: number;
  computation_time_ms: number;
  coordinate_reference_system: string;
  scientific_limitation: string;
  terrain_profile: RouteTerrainProfile;
};

export class RoutePlanApiError extends Error {
  readonly status: number | null;
  readonly kind:
    | "infeasible"
    | "unavailable"
    | "network"
    | "timeout"
    | "invalid-response"
    | "http";

  constructor(
    message: string,
    status: number | null,
    kind:
      | "infeasible"
      | "unavailable"
      | "network"
      | "timeout"
      | "invalid-response"
      | "http",
  ) {
    super(message);
    this.name = "RoutePlanApiError";
    this.status = status;
    this.kind = kind;
  }
}

export const slopePreviewUrl =
  `${API_BASE}/api/terrain/jezero/slope/preview`;

export function terrainAssetUrl(path: string): string {
  return `${API_BASE}${path}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isRoutePlanResponse(value: unknown): value is RoutePlanResponse {
  if (!isRecord(value) || !Array.isArray(value.route_coordinates)) {
    return false;
  }

  return (
    value.feasible === true &&
    value.route_coordinates.every(
      (coordinate) =>
        isRecord(coordinate) &&
        isFiniteNumber(coordinate.x) &&
        isFiniteNumber(coordinate.y),
    ) &&
    typeof value.path_cell_count === "number" &&
    Number.isInteger(value.path_cell_count) &&
    value.path_cell_count > 0 &&
    value.route_coordinates.length === value.path_cell_count &&
    isFiniteNumber(value.path_distance_m) &&
    value.path_distance_m >= 0 &&
    isFiniteNumber(value.maximum_encountered_slope_degrees) &&
    value.maximum_encountered_slope_degrees >= 0 &&
    value.maximum_encountered_slope_degrees <= 90 &&
    isFiniteNumber(value.average_encountered_slope_degrees) &&
    value.average_encountered_slope_degrees >= 0 &&
    value.average_encountered_slope_degrees <= 90 &&
    isFiniteNumber(value.estimated_terrain_movement_cost) &&
    value.estimated_terrain_movement_cost >= 0 &&
    isFiniteNumber(value.computation_time_ms) &&
    value.computation_time_ms >= 0 &&
    typeof value.coordinate_reference_system === "string" &&
    value.coordinate_reference_system.length > 0 &&
    typeof value.scientific_limitation === "string" &&
    value.scientific_limitation.length > 0 &&
    isRouteTerrainProfile(value.terrain_profile)
  );
}

function isRouteTerrainProfile(value: unknown): value is RouteTerrainProfile {
  if (
    !isRecord(value) ||
    !isRecord(value.thresholds) ||
    !isRecord(value.slope_distribution_degrees) ||
    !Array.isArray(value.categories) ||
    !Array.isArray(value.consecutive_high_slope_segments) ||
    !isRecord(value.analysis_metadata)
  ) {
    return false;
  }

  const thresholds = value.thresholds;
  const distribution = value.slope_distribution_degrees;
  return (
    isFiniteNumber(thresholds.low_max_degrees) &&
    isFiniteNumber(thresholds.moderate_max_degrees) &&
    isFiniteNumber(thresholds.high_max_degrees) &&
    isFiniteNumber(distribution.minimum) &&
    isFiniteNumber(distribution.average) &&
    isFiniteNumber(distribution.maximum) &&
    Number.isInteger(value.high_slope_segment_count) &&
    value.high_slope_segment_count ===
      value.consecutive_high_slope_segments.length &&
    value.categories.every(isRouteProfileCategory) &&
    value.consecutive_high_slope_segments.every(isRouteSlopeSegment) &&
    (value.highest_slope_segment === null ||
      isRouteSlopeSegment(value.highest_slope_segment))
  );
}

function isRouteProfileCategory(value: unknown): value is RouteProfileCategory {
  return (
    isRecord(value) &&
    Number.isInteger(value.code) &&
    typeof value.name === "string" &&
    (value.minimum_exclusive_degrees === null ||
      isFiniteNumber(value.minimum_exclusive_degrees)) &&
    (value.maximum_inclusive_degrees === null ||
      isFiniteNumber(value.maximum_inclusive_degrees)) &&
    typeof value.color === "string" &&
    Number.isInteger(value.cell_count) &&
    isFiniteNumber(value.percentage_of_route_cells) &&
    isFiniteNumber(value.distance_m)
  );
}

function isRouteSlopeSegment(value: unknown): value is RouteSlopeSegment {
  return (
    isRecord(value) &&
    Number.isInteger(value.start_route_cell_index) &&
    Number.isInteger(value.end_route_cell_index) &&
    Number.isInteger(value.cell_count) &&
    isFiniteNumber(value.distance_m) &&
    isFiniteNumber(value.maximum_slope_degrees) &&
    Array.isArray(value.start_coordinate) &&
    value.start_coordinate.length === 2 &&
    value.start_coordinate.every(isFiniteNumber) &&
    Array.isArray(value.end_coordinate) &&
    value.end_coordinate.length === 2 &&
    value.end_coordinate.every(isFiniteNumber)
  );
}

function isTraversabilityCategory(
  value: unknown,
): value is TraversabilityCategory {
  return (
    isRecord(value) &&
    Number.isInteger(value.code) &&
    typeof value.name === "string" &&
    (value.minimum_exclusive_degrees === null ||
      isFiniteNumber(value.minimum_exclusive_degrees)) &&
    (value.maximum_inclusive_degrees === null ||
      isFiniteNumber(value.maximum_inclusive_degrees)) &&
    typeof value.color === "string" &&
    Number.isInteger(value.cell_count) &&
    isFiniteNumber(value.percentage_of_valid_cells)
  );
}

function isTraversabilitySummary(
  value: unknown,
): value is TraversabilitySummary {
  return (
    isRecord(value) &&
    Number.isInteger(value.width) &&
    Number.isInteger(value.height) &&
    typeof value.crs === "string" &&
    isRecord(value.resolution) &&
    isFiniteNumber(value.resolution.x) &&
    isFiniteNumber(value.resolution.y) &&
    typeof value.resolution.unit === "string" &&
    Array.isArray(value.transform) &&
    value.transform.every(isFiniteNumber) &&
    Array.isArray(value.category_definitions) &&
    value.category_definitions.length === 4 &&
    value.category_definitions.every(isTraversabilityCategory) &&
    Number.isInteger(value.valid_cell_count) &&
    Number.isInteger(value.nodata_cell_count) &&
    isRecord(value.analysis_metadata) &&
    typeof value.raster_url === "string" &&
    typeof value.preview_url === "string"
  );
}

function isProvenanceManifest(value: unknown): value is ProvenanceManifest {
  if (
    !isRecord(value) ||
    typeof value.manifest_id !== "string" ||
    typeof value.analysis_status !== "string" ||
    !Array.isArray(value.processing_pipeline) ||
    !Array.isArray(value.derived_products) ||
    !Array.isArray(value.scientific_limitations)
  ) {
    return false;
  }
  const source = value.source_dataset;
  if (!isRecord(source)) return false;
  const asset = source.original_asset;
  if (
    !isRecord(asset) ||
    !isRecord(asset.raster_metadata) ||
    !isRecord(asset.checksum)
  ) {
    return false;
  }
  return (
    typeof source.record_id === "string" &&
    typeof source.dataset_title === "string" &&
    typeof source.version === "string" &&
    typeof source.provider === "string" &&
    typeof source.publisher === "string" &&
    typeof source.product_identifier === "string" &&
    typeof source.product_url === "string" &&
    typeof source.publication_date === "string" &&
    typeof source.recommended_citation === "string" &&
    isRecord(source.nominal_product_resolution) &&
    isFiniteNumber(source.nominal_product_resolution.value) &&
    typeof source.nominal_product_resolution.unit === "string" &&
    typeof asset.filename === "string" &&
    typeof asset.availability_at_capture === "string" &&
    Number.isInteger(asset.raster_metadata.width) &&
    Number.isInteger(asset.raster_metadata.height) &&
    Array.isArray(asset.raster_metadata.data_types) &&
    (asset.raster_metadata.nodata === null ||
      isFiniteNumber(asset.raster_metadata.nodata)) &&
    (asset.checksum.sha256 === null ||
      typeof asset.checksum.sha256 === "string") &&
    typeof asset.checksum.status === "string" &&
    value.processing_pipeline.every(
      (stage) =>
        isRecord(stage) &&
        typeof stage.stage_id === "string" &&
        typeof stage.operation === "string" &&
        Array.isArray(stage.known_limitations),
    ) &&
    value.derived_products.every(
      (product) =>
        isRecord(product) &&
        typeof product.record_id === "string" &&
        typeof product.filename === "string" &&
        typeof product.product_type === "string" &&
        isRecord(product.generated_at) &&
        typeof product.generated_at.value === "string" &&
        isRecord(product.checksum) &&
        typeof product.checksum.sha256 === "string",
    ) &&
    value.scientific_limitations.every(
      (limitation) => typeof limitation === "string",
    ) &&
    typeof value.ai_assisted_development_disclosure === "string"
  );
}

function isProvenanceProductStatus(
  value: unknown,
): value is ProvenanceProductStatus {
  return (
    isRecord(value) &&
    typeof value.record_id === "string" &&
    typeof value.filename === "string" &&
    typeof value.available === "boolean" &&
    typeof value.verification_status === "string" &&
    typeof value.checksum_status === "string" &&
    typeof value.metadata_status === "string" &&
    (typeof value.expected_sha256 === "string" ||
      value.expected_sha256 === null) &&
    (typeof value.actual_sha256 === "string" ||
      value.actual_sha256 === null) &&
    (isFiniteNumber(value.size_bytes) || value.size_bytes === null)
  );
}

function isProvenanceReport(value: unknown): value is ProvenanceReport {
  return (
    isRecord(value) &&
    isProvenanceManifest(value.manifest) &&
    typeof value.manifest_status === "string" &&
    isRecord(value.source_asset_status) &&
    typeof value.source_asset_status.filename === "string" &&
    typeof value.source_asset_status.availability === "string" &&
    typeof value.source_asset_status.checksum_status === "string" &&
    Array.isArray(value.product_verification) &&
    value.product_verification.every(isProvenanceProductStatus)
  );
}

export async function fetchProvenance(
  signal?: AbortSignal,
): Promise<ProvenanceReport> {
  const response = await fetchApi<unknown>("/api/provenance", signal);
  if (!isProvenanceReport(response)) {
    throw new Error("The provenance API response did not match the expected format.");
  }
  return response;
}

export async function fetchTraversability(
  signal?: AbortSignal,
): Promise<TraversabilitySummary> {
  const response = await fetchApi<unknown>(
    "/api/terrain/jezero/traversability",
    signal,
  );
  if (!isTraversabilitySummary(response)) {
    throw new Error(
      "The traversability API response did not match the expected format.",
    );
  }
  return response;
}

function getErrorDetail(body: unknown): string | null {
  if (!isRecord(body) || !("detail" in body)) return null;
  const { detail } = body;
  if (typeof detail === "string") return detail;
  if (isRecord(detail) && typeof detail.message === "string") {
    return detail.message;
  }
  return null;
}

export async function planTerrainRoute(
  request: RoutePlanRequest,
  signal?: AbortSignal,
): Promise<RoutePlanResponse> {
  const requestSignal = createRequestSignal(signal);
  try {
    let response: Response;
    try {
      response = await fetch(`${API_BASE}/api/route/plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
        signal: requestSignal.signal,
      });
    } catch (error) {
      if (requestSignal.signal.aborted && signal?.aborted) throw error;
      if (requestSignal.timedOut()) {
        throw new RoutePlanApiError(
          `The route-planning API did not respond within ${API_REQUEST_TIMEOUT_MS / 1000} seconds.`,
          null,
          "timeout",
        );
      }
      const reason = error instanceof Error ? ` ${error.message}` : "";
      throw new RoutePlanApiError(
        `Could not connect to the ARES route-planning API.${reason}`,
        null,
        "network",
      );
    }

    let body: unknown;
    try {
      body = await response.json();
    } catch (error) {
      if (requestSignal.signal.aborted && signal?.aborted) throw error;
      if (requestSignal.timedOut()) {
        throw new RoutePlanApiError(
          `The route-planning API did not respond within ${API_REQUEST_TIMEOUT_MS / 1000} seconds.`,
          response.status,
          "timeout",
        );
      }
      if (response.ok) {
        throw new RoutePlanApiError(
          "The route-planning API returned invalid JSON.",
          response.status,
          "invalid-response",
        );
      }
      body = null;
    }

    if (!response.ok) {
      const detail = getErrorDetail(body);
      if (response.status === 422) {
        throw new RoutePlanApiError(
          detail ?? "The selected endpoints do not have a feasible route.",
          response.status,
          "infeasible",
        );
      }
      if (response.status === 503) {
        throw new RoutePlanApiError(
          detail ?? "Terrain data is unavailable for route planning.",
          response.status,
          "unavailable",
        );
      }
      throw new RoutePlanApiError(
        detail ?? `Route-planning request failed (HTTP ${response.status}).`,
        response.status,
        "http",
      );
    }

    if (!isRoutePlanResponse(body)) {
      throw new RoutePlanApiError(
        "The route-planning API response did not match the expected format.",
        response.status,
        "invalid-response",
      );
    }
    return body;
  } finally {
    requestSignal.dispose();
  }
}

export async function fetchApi<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T> {
  const requestSignal = createRequestSignal(signal);
  try {
    let response: Response;
    try {
      response = await fetch(`${API_BASE}${path}`, {
        signal: requestSignal.signal,
      });
    } catch (error) {
      if (requestSignal.signal.aborted && signal?.aborted) throw error;
      if (requestSignal.timedOut()) {
        throw new Error(
          `${path}: Request timed out after ${API_REQUEST_TIMEOUT_MS / 1000} seconds.`,
          { cause: error },
        );
      }
      throw error;
    }

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
      } catch (error) {
        if (requestSignal.signal.aborted && signal?.aborted) throw error;
        if (requestSignal.timedOut()) {
          throw new Error(
            `${path}: Request timed out after ${API_REQUEST_TIMEOUT_MS / 1000} seconds.`,
            { cause: error },
          );
        }
        detail = response.statusText || "Response body was not valid JSON";
      }
      throw new Error(`${path}: ${detail || `HTTP ${response.status}`}`);
    }

    try {
      return (await response.json()) as T;
    } catch (error) {
      if (requestSignal.signal.aborted && signal?.aborted) throw error;
      if (requestSignal.timedOut()) {
        throw new Error(
          `${path}: Request timed out after ${API_REQUEST_TIMEOUT_MS / 1000} seconds.`,
          { cause: error },
        );
      }
      throw new Error(`${path}: Response body was not valid JSON.`, {
        cause: error,
      });
    }
  } finally {
    requestSignal.dispose();
  }
}
