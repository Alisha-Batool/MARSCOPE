
import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  Activity,
  Battery,
  Check,
  ChevronDown,
  CircleHelp,
  Clock3,
  Layers3,
  MapPin,
  Minus,
  Plus,
  RotateCcw,
  Send,
  Shield,
  Sparkles,
  Target,
  X,
} from "lucide-react";
import "./styles.css";
import {
  assessRoutes,
  demoRouteCandidates,
  missionObjectives,
  type MissionObjective,
  type MissionPriorities,
  type RouteAssessment,
} from "./services/missionPlanner";
import {
  fetchApi,
  slopePreviewUrl,
  type ApiHealth,
  type SlopeMetadata,
  type TerrainSummary,
} from "./services/terrainApi";

const mapLayers = [
  "Terrain overview · illustrative",
  "Slope risk · derived DEM",
  "DEMO — TARGET DATA NOT INTEGRATED",
] as const;

const routePaths: Record<string, string> = {
  alpha: "M190 405 C260 370 305 320 405 280 S570 300 670 400",
  bravo: "M190 405 C250 345 295 270 390 260 S550 270 670 400",
  charlie: "M190 405 C290 430 360 365 445 345 S565 355 670 400",
};

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function App() {
  const [apiStatus, setApiStatus] = useState<
    "checking" | "online" | "offline"
  >("checking");
  const [dataStatus, setDataStatus] = useState("unknown");
  const [terrainSummary, setTerrainSummary] = useState<TerrainSummary | null>(
    null,
  );
  const [slopeMetadata, setSlopeMetadata] = useState<SlopeMetadata | null>(
    null,
  );
  const [terrainLoading, setTerrainLoading] = useState(true);
  const [terrainError, setTerrainError] = useState("");
  const [slopePreviewLoaded, setSlopePreviewLoaded] = useState(false);
  const [slopePreviewError, setSlopePreviewError] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    async function loadTerrain() {
      const [healthResult, summaryResult, slopeResult] = await Promise.allSettled([
        fetchApi<ApiHealth>("/api/health", controller.signal),
        fetchApi<TerrainSummary>(
          "/api/terrain/jezero/summary",
          controller.signal,
        ),
        fetchApi<SlopeMetadata>(
          "/api/terrain/jezero/slope",
          controller.signal,
        ),
      ]);
      if (cancelled) return;

      if (healthResult.status === "fulfilled") {
        setApiStatus("online");
        setDataStatus(healthResult.value.data_status);
      } else {
        setApiStatus("offline");
        setDataStatus("unknown");
      }

      const errors: string[] = [];
      if (summaryResult.status === "fulfilled") {
        setTerrainSummary(summaryResult.value);
      } else {
        errors.push(getErrorMessage(summaryResult.reason));
      }
      if (slopeResult.status === "fulfilled") {
        setSlopeMetadata(slopeResult.value);
      } else {
        errors.push(getErrorMessage(slopeResult.reason));
      }
      if (healthResult.status === "rejected") {
        errors.unshift(getErrorMessage(healthResult.reason));
      }
      setTerrainError(errors.join(" · "));
      setTerrainLoading(false);
    }

    void loadTerrain();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, []);

  const [maxDuration, setMaxDuration] = useState(6);
  const [minOxygen, setMinOxygen] = useState(20);
  const [maxSlope, setMaxSlope] = useState(18);
  const [priorities, setPriorities] = useState<MissionPriorities>({
    science: 86,
    safety: 92,
    time: 48,
    energy: 66,
  });
  const [selectedRouteId, setSelectedRouteId] = useState("alpha");
  const [layer, setLayer] = useState<(typeof mapLayers)[number]>(mapLayers[0]);
  const [objective, setObjective] = useState<MissionObjective>(
    missionObjectives[0],
  );
  const [targetMenuOpen, setTargetMenuOpen] = useState(false);
  const [target, setTarget] = useState("Jezero Crater · Delta scenario");
  const [waypointsVisible, setWaypointsVisible] = useState(true);
  const [targetLayersVisible, setTargetLayersVisible] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [mapOffset, setMapOffset] = useState({ x: 0, y: 0 });
  const [briefing, setBriefing] = useState(
    "Route candidates and their metrics are illustrative scenarios, not measured traverses. Terrain provenance and derived slope statistics load from the Jezero backend products.",
  );
  const [question, setQuestion] = useState("");

  const routeResults = useMemo<RouteAssessment[]>(() => {
    return assessRoutes(
      demoRouteCandidates,
      { maxDuration, minOxygen, maxSlope },
      priorities,
      objective,
    );
  }, [maxDuration, minOxygen, maxSlope, priorities, objective]);

  const selected =
    routeResults.find((route) => route.id === selectedRouteId) ??
    routeResults[0];

  const feasibleRoutes = routeResults.filter((route) => route.feasible);
  const bestRoute = feasibleRoutes[0] ?? null;

  function updateConstraints() {
    if (!bestRoute) {
      setBriefing(
        "No route meets the current mission profile. Relax the safety or timing constraints and re-evaluate the traverse plan.",
      );
      return;
    }

    setSelectedRouteId(bestRoute.id);
    setBriefing(
      `${bestRoute.name} is the highest-scoring feasible illustrative scenario (score ${Math.round(bestRoute.score)}/100). Priorities: science ${priorities.science}%, safety ${priorities.safety}%, time ${priorities.time}%, energy ${priorities.energy}%. The score uses the selected objective and active hard limits; route inputs are synthetic and not measured from the DEM.`,
    );
  }

  function askCommander(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!question.trim()) return;

    const safetyText = selected.feasible ? "meets" : "does not meet";

    setBriefing(
      `Question: "${question.trim()}" ${selected.name} ${safetyText} the current constraints for ${objective.toLowerCase()}. Its deterministic illustrative score is ${Math.round(selected.score)}/100; ${selected.feasible ? "it is eligible for recommendation." : `it is rejected because ${selected.failures.join(", ")}.`} These route inputs are synthetic, not live terrain measurements.`,
    );

    setQuestion("");
  }

  const missionCards = [
    { label: "Mission objective", value: objective },
    {
      label: "Feasible routes",
      value: `${feasibleRoutes.length}/${demoRouteCandidates.length}`,
    },
    {
      label: "Best route score",
      value: bestRoute ? `${Math.round(bestRoute.score)}` : "N/A",
    },
    {
      label: "Terrain data",
      value: terrainSummary ? `${terrainSummary.analysis_status} DEM` : "Unavailable",
    },
  ];

  const isSlopeLayer = layer === mapLayers[1];
  const isScienceLayer = layer === mapLayers[2];
  const mapTransform = `translate(${mapOffset.x}px, ${mapOffset.y}px) scale(${zoom})`;

  function updatePriority(key: keyof MissionPriorities, value: number) {
    setPriorities((current) => ({ ...current, [key]: value }));
  }

  function zoomMap(amount: number) {
    setZoom((current) => Math.max(0.75, Math.min(2.5, current + amount)));
  }

  function moveMap(x: number, y: number) {
    setMapOffset((current) => ({ x: current.x + x, y: current.y + y }));
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">A</div>
          <div>
            <div className="brand-name">
              A<span>RES</span>
            </div>
            <div className="brand-subtitle">
              MISSION PLANNING · TERRAIN INTELLIGENCE
            </div>
          </div>
        </div>

        <div className="system-status">
          <span
            className={`status-dot ${apiStatus === "offline" ? "offline" : ""}`}
          />
          {apiStatus === "checking"
            ? "CHECKING API"
            : apiStatus === "online"
              ? `API ONLINE · DATA ${dataStatus.toUpperCase()}`
              : "API OFFLINE"}
        </div>

        <button
          className="target-select"
          type="button"
          aria-expanded={targetMenuOpen}
          onClick={() => setTargetMenuOpen((open) => !open)}
        >
          <span>
            <small>MISSION TARGET</small>
            <strong>{target}</strong>
          </span>
          <ChevronDown size={15} />
        </button>
        {targetMenuOpen && (
          <div className="target-menu">
            <div className="section-label">AVAILABLE TERRAIN SITE</div>
            <button
              type="button"
              onClick={() => {
                setTarget("Jezero Crater · Delta scenario");
                setTargetMenuOpen(false);
              }}
            >
              <strong>Jezero Crater · Delta scenario</strong>
              <small>Illustrative route scenarios; processed terrain below</small>
            </button>
          </div>
        )}

        <div className="top-metric">
          <Clock3 size={14} />
          <span>
            <small>SCENARIO DURATION</small>
            <strong>{selected.duration} H · DEMO</strong>
          </span>
        </div>

        <div className="top-metric">
          <Battery size={15} />
          <span>
            <small>ENERGY SCORE</small>
            <strong>
              {Math.round(selected.energyScore)}/100 · SIMULATED PROXY
            </strong>
          </span>
        </div>

        <div className="top-metric oxygen">
          <Activity size={14} />
          <span>
            <small>O₂ RESERVE</small>
            <strong>{selected.oxygen}% · DEMO</strong>
          </span>
        </div>

        <div className="eva-badge">
          <span /> EVA SIMULATION
        </div>
      </header>

      <div className="workspace">
        <aside className="left-panel">
          <div className="panel-heading">
            <Target size={14} />
            <span>MISSION PARAMETERS &amp; CONSTRAINTS</span>
            <X size={14} className="muted-icon" />
          </div>

          <section className="control-section">
            <div className="section-label">01 / PRIMARY OBJECTIVE</div>

            <div className="objective-select-wrap">
              <select
                className="objective-select"
                value={objective}
                onChange={(event) => {
                  const selectedObjective = missionObjectives.find(
                    (item) => item === event.target.value,
                  );
                  if (selectedObjective) setObjective(selectedObjective);
                }}
                aria-label="Select mission objective"
              >
                {missionObjectives.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
              <ChevronDown size={14} className="objective-chevron" />
            </div>

            <div className="objective-meta">
              <Sparkles size={13} /> SCIENCE
              <span>{objective.toUpperCase()}</span>
            </div>
          </section>

          <section className="control-section">
            <div className="section-label">
              02 / HARD CONSTRAINTS{" "}
              <span className="section-count">3 ACTIVE</span>
            </div>

            <div className="constraint-grid">
              <label className="constraint-card">
                <span>MAX DURATION</span>
                <div>
                  <input
                    type="number"
                    min="1"
                    max="12"
                    step="0.5"
                    value={maxDuration}
                    onChange={(event) => {
                      const value = event.currentTarget.valueAsNumber;
                      if (Number.isFinite(value)) {
                        setMaxDuration(Math.max(1, Math.min(12, value)));
                      }
                    }}
                  />
                  <small>HRS</small>
                </div>
              </label>

              <label className="constraint-card">
                <span>MIN O₂ MARGIN</span>
                <div>
                  <input
                    type="number"
                    min="0"
                    max="80"
                    value={minOxygen}
                    onChange={(event) => {
                      const value = event.currentTarget.valueAsNumber;
                      if (Number.isFinite(value)) {
                        setMinOxygen(Math.max(0, Math.min(80, value)));
                      }
                    }}
                  />
                  <small>%</small>
                </div>
              </label>

              <label className="constraint-card">
                <span>MAX SLOPE LIMIT</span>
                <div>
                  <input
                    type="number"
                    min="1"
                    max="40"
                    value={maxSlope}
                    onChange={(event) => {
                      const value = event.currentTarget.valueAsNumber;
                      if (Number.isFinite(value)) {
                        setMaxSlope(Math.max(1, Math.min(40, value)));
                      }
                    }}
                  />
                  <small>°</small>
                </div>
              </label>
            </div>

            <button
              className="recompute-button"
              type="button"
              onClick={updateConstraints}
            >
              <Activity size={14} /> OPTIMIZE ROUTE
            </button>
          </section>

          <section className="control-section tradeoffs">
            <div className="section-label">
              03 / TRADE-OFF PRIORITIES{" "}
              <span className="section-count">ACTIVE</span>
            </div>

            <Priority
              label="Scientific value"
              value={priorities.science}
              color="cyan"
              onChange={(value) => updatePriority("science", value)}
            />
            <Priority
              label="Safety / low risk"
              value={priorities.safety}
              color="green"
              onChange={(value) => updatePriority("safety", value)}
            />
            <Priority
              label="Time efficiency"
              value={priorities.time}
              color="orange"
              onChange={(value) => updatePriority("time", value)}
            />
            <Priority
              label="Energy conservation"
              value={priorities.energy}
              color="purple"
              onChange={(value) => updatePriority("energy", value)}
            />

            <p className="assumption-note">
              Priorities re-rank eligible illustrative scenarios using
              objective value, safety, duration and a distance/slope energy
              proxy.
            </p>
          </section>

          <div className="panel-footnote">
            <CircleHelp size={13} />
            Mission limits are simulation assumptions intended for operational
            planning review.
          </div>
        </aside>

        <section className="map-panel">
          <div className="map-toolbar">
            <div className="layer-tabs">
              {mapLayers.map((item) => (
                <button
                  key={item}
                  type="button"
                  className={layer === item ? "layer-tab active" : "layer-tab"}
                  onClick={() => {
                    setLayer(item);
                    setSlopePreviewLoaded(false);
                    setSlopePreviewError(false);
                  }}
                  aria-pressed={layer === item}
                >
                  {item}
                </button>
              ))}
            </div>

            <button
              type="button"
              className="toolbar-button"
              aria-pressed={waypointsVisible}
              onClick={() => setWaypointsVisible((visible) => !visible)}
            >
              <Target size={14} /> WAYPOINTS
            </button>
            <button
              type="button"
              className="toolbar-button"
              aria-pressed={targetLayersVisible}
              onClick={() => setTargetLayersVisible((visible) => !visible)}
            >
              <Layers3 size={14} /> TARGET LAYERS
            </button>
          </div>

          <div
            className="map-canvas"
            onWheel={(event) => {
              event.preventDefault();
              zoomMap(event.deltaY < 0 ? 0.1 : -0.1);
            }}
          >
            <div className="map-viewport" style={{ transform: mapTransform }}>
            <div className="map-coordinate">
              {isSlopeLayer ? (
                <>
                  {slopeMetadata?.region.toUpperCase() ?? "JEZERO CRATER"}
                  <br />
                  {slopeMetadata
                    ? `${slopeMetadata.width} × ${slopeMetadata.height} px · SLOPE IN DEGREES`
                    : "LOADING SLOPE METADATA"}
                </>
              ) : (
                <>
                  JEZERO CRATER
                  <br />
                  ROUTE SCENARIO · SYNTHETIC GEOMETRY
                </>
              )}
            </div>

            {isSlopeLayer && (
              <div className="slope-layer">
                <img
                  className="slope-raster"
                  src={slopePreviewUrl}
                  alt="Jezero Crater terrain slope raster derived from the MOLA-HRSC blended DEM"
                  onLoad={() => {
                    setSlopePreviewLoaded(true);
                    setSlopePreviewError(false);
                  }}
                  onError={() => {
                    setSlopePreviewLoaded(false);
                    setSlopePreviewError(true);
                  }}
                />

                <div className="slope-layer-label">
                  {slopePreviewLoaded
                    ? "TERRAIN SLOPE · DERIVED RASTER"
                    : slopePreviewError
                      ? "TERRAIN RASTER UNAVAILABLE"
                      : "LOADING TERRAIN RASTER..."}
                </div>

                <div className="slope-legend">
                  <strong>SLOPE · DEGREES</strong>
                  <span>
                    <i className="slope-swatch slope-low" /> 0–5°
                  </span>
                  <span>
                    <i className="slope-swatch slope-moderate" /> 5–12°
                  </span>
                  <span>
                    <i className="slope-swatch slope-high" /> 12–18°
                  </span>
                  <span>
                    <i className="slope-swatch slope-critical" /> Above 18°
                  </span>
                </div>

                {slopePreviewError && (
                  <div className="slope-provisional">
                    Unable to load raster. Check that FastAPI is running on port
                    8000.
                  </div>
                )}

                {!slopePreviewError && (
                  <div className="slope-provisional">
                    {terrainSummary?.vertical_units_verified
                      ? "DERIVED SLOPE · SOURCE VERTICAL UNITS VERIFIED"
                      : "PROVISIONAL · DEM VERTICAL UNITS NOT YET VERIFIED"}
                  </div>
                )}
              </div>
            )}

            {!isSlopeLayer && (
              <>
                <div className="north-arrow">
                  N<span>↑</span>
                </div>

                <div className="sector sector-one">SECTOR 1A</div>
                <div className="sector sector-two">SECTOR 2C</div>
                <div className="sector sector-three">SECTOR 3B</div>
                <div className="sector sector-four">SECTOR 4</div>

                <svg
                  className="terrain"
                  viewBox="0 0 900 550"
                  preserveAspectRatio="none"
                  aria-hidden="true"
                >
                  <defs>
                    <radialGradient id="terrainGlow">
                      <stop offset="0" stopColor="#bd6426" stopOpacity=".16" />
                      <stop offset="1" stopColor="#bd6426" stopOpacity="0" />
                    </radialGradient>
                  </defs>

                  <ellipse
                    cx="490"
                    cy="280"
                    rx="320"
                    ry="240"
                    fill="url(#terrainGlow)"
                  />

                  {[0, 1, 2, 3, 4].map((i) => (
                    <ellipse
                      key={i}
                      cx="485"
                      cy="270"
                      rx={110 + i * 38}
                      ry={70 + i * 26}
                      fill="none"
                      stroke="#8f613f"
                      strokeOpacity=".22"
                    />
                  ))}

                  <path
                    d="M170 165 C230 220 190 300 250 385 M660 130 C600 210 690 295 615 395"
                    fill="none"
                    stroke="#795138"
                    strokeWidth="8"
                    strokeOpacity=".24"
                  />

                  <path
                    d={routePaths[selected.id]}
                    fill="none"
                    stroke={selected.color}
                    strokeWidth="5"
                  />

                  <path
                    d="M190 405 C310 445 490 470 670 400"
                    fill="none"
                    stroke="#34d399"
                    strokeWidth="4"
                    strokeDasharray="8 9"
                    opacity={selected.id === "charlie" ? "0.35" : "0.9"}
                  />

                  {waypointsVisible && (
                    <>
                      <circle
                        cx="405"
                        cy="280"
                        r="14"
                        fill="#f2aa22"
                        fillOpacity=".18"
                        stroke="#f2aa22"
                        strokeWidth="2"
                      />
                      <circle cx="405" cy="280" r="5" fill="#f2aa22" />

                      <circle
                        cx="535"
                        cy="330"
                        r="10"
                        fill="#ff6d50"
                        fillOpacity=".16"
                        stroke="#ff6d50"
                        strokeWidth="2"
                      />
                      <circle cx="535" cy="330" r="4" fill="#ff6d50" />
                    </>
                  )}
                </svg>

                {waypointsVisible && (
                  <div className="base-marker">
                    <MapPin size={17} />
                    <strong>ARES BASE · DEMO</strong>
                  </div>
                )}

                {targetLayersVisible && (
                  <div className="target-card">
                  <div className="target-card-title">
                    <strong>TARGET A · DELTA OUTCROP</strong>
                    <span>ILLUSTRATIVE</span>
                  </div>
                  <div className="target-stats">
                    <span>
                      SCIENCE SCORE<strong>{selected.scienceScore}/100</strong>
                    </span>
                    <span>
                      MAX SLOPE<strong>{selected.maxSlope}°</strong>
                    </span>
                    <span>
                      ROUTE RISK<strong>{selected.hazard.toFixed(2)}</strong>
                    </span>
                    <span>
                      DISTANCE<strong>{selected.distance} KM</strong>
                    </span>
                  </div>
                </div>
                )}

                <div className="map-legend">
                  <span>
                    <i className="legend-line selected-line" />{" "}
                    {selected.name.toUpperCase()} · ACTIVE
                  </span>
                  <span>
                    <i className="legend-line alternate-line" /> ALT ROUTE · SYNTHETIC
                  </span>
                </div>
              </>
            )}

            {isScienceLayer && (
              <div className="science-layer-notice">
                <strong>DEMO — TARGET DATA NOT INTEGRATED</strong>
                <span>
                  The backend has no science-target endpoint. Target positions
                  and science scores are illustrative only, not measured
                  observations or NASA science-target data.
                </span>
              </div>
            )}

            <div className="map-disclaimer">
              {isSlopeLayer
                ? "PROVISIONAL DERIVED SLOPE · ROUTES CONCEPTUAL, NOT VALIDATED OR GEOREFERENCED"
                : `CONCEPTUAL ROUTES · NOT VALIDATED ROVER TRAVERSES OR GEOREFERENCED NAVIGATION · ${layer.toUpperCase()}`}
            </div>
            </div>

            <div className="map-controls" aria-label="Map navigation">
              <div className="map-pan-controls">
                <button
                  type="button"
                  aria-label="Pan map up"
                  onClick={() => moveMap(0, 40)}
                >
                  <ArrowUp size={13} />
                </button>
                <button
                  type="button"
                  aria-label="Pan map left"
                  onClick={() => moveMap(40, 0)}
                >
                  <ArrowLeft size={13} />
                </button>
                <button
                  type="button"
                  aria-label="Pan map down"
                  onClick={() => moveMap(0, -40)}
                >
                  <ArrowDown size={13} />
                </button>
                <button
                  type="button"
                  aria-label="Pan map right"
                  onClick={() => moveMap(-40, 0)}
                >
                  <ArrowRight size={13} />
                </button>
              </div>
              <button
                type="button"
                aria-label="Zoom out"
                onClick={() => zoomMap(-0.15)}
              >
                <Minus size={13} />
              </button>
              <span>{Math.round(zoom * 100)}%</span>
              <button
                type="button"
                aria-label="Zoom in"
                onClick={() => zoomMap(0.15)}
              >
                <Plus size={13} />
              </button>
              <button
                type="button"
                aria-label="Reset map view"
                onClick={() => {
                  setZoom(1);
                  setMapOffset({ x: 0, y: 0 });
                }}
              >
                <RotateCcw size={13} />
              </button>
            </div>
          </div>

          <div className="map-statusbar">
            <span>
              <i className="status-dot" /> {selected.name.toUpperCase()} SELECTED
            </span>
            <span>
              DATA: {isSlopeLayer ? "DERIVED DEM RASTER" : "SIMULATED"}
            </span>
            <span>GRID: ILLUSTRATIVE MARS SCENARIO</span>
            <span className="right-status">
              <i className="status-dot" /> WHAT-IF READY
            </span>
          </div>
        </section>

        <aside className="right-panel">
          <div className="right-section selected-strategy">
            <div className="section-label">SELECTED STRATEGY</div>
            <div className="route-title">{selected.name.toUpperCase()}</div>

            <p className="route-summary">
              {selected.feasible
                ? "This illustrative scenario satisfies the active hard limits. Its score ranks it against other feasible scenarios; it is not a measured traverse."
                : `Rejected by hard limits: ${selected.failures.join("; ")}.`}
            </p>

            <div className="stats-grid">
              {missionCards.map((card) => (
                <div key={card.label} className="metric-card">
                  <small>{card.label}</small>
                  <strong>{card.value}</strong>
                </div>
              ))}
            </div>

            <div className="validity-label">
              <span>DECISION VALIDITY</span>
              <strong>{selected.feasible ? "CONFIGURED" : "REVIEW"}</strong>
            </div>

            <div className="validity-bar">
              <i style={{ width: `${Math.min(selected.score, 100)}%` }} />
            </div>

            <p className="validity-note">
              Deterministic score {Math.round(selected.score)}/100 · science{" "}
              {Math.round(selected.scienceScore)} · safety{" "}
              {Math.round(selected.safetyScore)} · time{" "}
              {Math.round(selected.timeScore)} · simulated energy proxy{" "}
              {Math.round(selected.energyScore)}. Time, oxygen and energy
              metrics are illustrative scenario inputs; energy uses synthetic
              distance, route slope and duration.
            </p>
          </div>

          <div className="right-section">
            <div className="section-label">
              ROUTE RANKING · ILLUSTRATIVE · DURATION/O₂ SIMULATED
            </div>

            {routeResults.length > 0 ? (
              <div className="route-list">
                {routeResults.map((route, index) => (
                <button
                  key={route.id}
                  type="button"
                  onClick={() => {
                    setSelectedRouteId(route.id);
                    setBriefing(
                      route.feasible
                        ? `${route.name} selected (rank ${index + 1}, score ${Math.round(route.score)}/100). Objective value ${route.scienceScore}/100, safety ${Math.round(route.safetyScore)}/100, time ${Math.round(route.timeScore)}/100 and energy proxy ${Math.round(route.energyScore)}/100 contribute according to the active priorities. Inputs are illustrative, not DEM-derived route measurements.`
                        : `${route.name} selected for inspection but rejected by hard limits: ${route.failures.join("; ")}. Its score is not eligible for recommendation.`,
                    );
                  }}
                  className={`route-option ${
                    selectedRouteId === route.id ? "chosen" : ""
                  }`}
                  aria-pressed={selectedRouteId === route.id}
                >
                  <span
                    className={`route-status ${route.feasible ? "ok" : "bad"}`}
                  >
                    {route.feasible ? <Check size={13} /> : <X size={13} />}
                  </span>

                  <span className="route-option-main">
                    <strong>
                      #{index + 1} {route.name}
                      {bestRoute?.id === route.id ? " · RECOMMENDED" : ""}
                    </strong>
                    <small>
                      {route.distance} km · {route.duration} h · {route.oxygen}%
                      O₂
                    </small>
                    {!route.feasible && (
                      <small className="failure">
                        Fails: {route.failures.join(", ")}
                      </small>
                    )}
                  </span>

                  <span className="route-score">{Math.round(route.score)}</span>
                </button>
              ))}
              </div>
            ) : (
              <p className="empty-state">No route candidates are available.</p>
            )}

            <div
              className={`feasibility-callout ${
                selected.feasible ? "" : "warning"
              }`}
            >
              <Shield size={15} />
              <span>
                {selected.feasible
                  ? `Selected scenario passes all active limits. ${bestRoute?.id === selected.id ? "It is currently recommended." : "Optimize to select the current top-ranked feasible scenario."}`
                  : `This scenario fails: ${selected.failures.join("; ")}.`}
              </span>
            </div>
          </div>

          <div className="right-section">
            <div className="section-label">
              TERRAIN DATA &amp; PROVENANCE
            </div>

            <p className="provenance-note">
              MOLA–HRSC Blended DEM Global 200m v2 · 200 m/pixel · MOLA
              (NASA Mars Global Surveyor) + HRSC (ESA Mars Express), distributed
              by USGS Astrogeology.
            </p>

            {terrainLoading ? (
              <p className="loading-state">Loading Jezero terrain products…</p>
            ) : terrainSummary ? (
              <div className="terrain-data">
                <p>
                  <strong>Source</strong>
                  <span>{terrainSummary.source}</span>
                </p>
                <p>
                  <strong>Derived slope</strong>
                  <span>
                    Mean {terrainSummary.mean_slope_degrees.toFixed(2)}° · P95{" "}
                    {terrainSummary.percentile_95_slope_degrees.toFixed(2)}° ·
                    max {terrainSummary.maximum_slope_degrees.toFixed(2)}°
                  </span>
                </p>
                <p>
                  <strong>Analysis</strong>
                  <span>
                    {terrainSummary.slope_method} ·{" "}
                    {terrainSummary.source_resolution_m} m source grid ·{" "}
                    {terrainSummary.valid_pixels.toLocaleString()} valid cells
                  </span>
                </p>
                <p>
                  <strong>Raster</strong>
                  <span>
                    {slopeMetadata
                      ? `${slopeMetadata.width} × ${slopeMetadata.height} pixels`
                      : "Metadata unavailable"}
                  </span>
                </p>
                <p>
                  <strong>Source resolution</strong>
                  <span>{terrainSummary.source_resolution_m} m/pixel</span>
                </p>
                <p>
                  <strong>Slope method</strong>
                  <span>{terrainSummary.slope_method}</span>
                </p>
                <p>
                  <strong>Valid cells</strong>
                  <span>{terrainSummary.valid_pixels.toLocaleString()}</span>
                </p>
                <p>
                  <strong>Slope units</strong>
                  <span>Degrees (°)</span>
                </p>
              </div>
            ) : (
              <p className="empty-state">
                Terrain summary unavailable. Start the FastAPI service and
                confirm the processed Jezero products exist.
              </p>
            )}
            {terrainError && (
              <p className="api-error" role="alert">
                API/data error: {terrainError}
              </p>
            )}
            <p className="provenance-caveat">
              {terrainSummary?.analysis_status.toUpperCase() ?? "PROVISIONAL"} ·
              Vertical units remain unverified. The slope analysis is derived
              from the DEM; route candidates and scores are synthetic
              illustrative inputs, not DEM-derived or mission-validated.
            </p>
          </div>

          <div className="right-section">
            <div className="section-label">NASA RESOURCES</div>
            <nav
              className="resource-links"
              aria-label="NASA and planetary data resources"
            >
              <a
                href="https://trek.nasa.gov/mars/"
                target="_blank"
                rel="noopener noreferrer"
              >
                NASA JPL Mars Trek
              </a>
              <a
                href="https://astrogeology-usgs.hub.arcgis.com/pages/interactive-maps-mars"
                target="_blank"
                rel="noopener noreferrer"
              >
                USGS–NASA Interactive Mars Geologic Maps
              </a>
              <a
                href="https://mars.nasa.gov/mars2020/multimedia/raw-images/"
                target="_blank"
                rel="noopener noreferrer"
              >
                Perseverance Raw Images
              </a>
            </nav>
          </div>

          <div className="right-section">
            <div className="section-label">
              COMMANDER BRIEFING <span className="demo-tag">LOCAL</span>
            </div>
            <div className="briefing-box" aria-live="polite">
              {briefing}
            </div>
          </div>

          <form className="commander-input" onSubmit={askCommander}>
            <Sparkles size={15} />
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask about the selected scenario..."
              aria-label="Ask about the selected route scenario"
            />
            <button
              type="submit"
              aria-label="Send question"
              disabled={!question.trim()}
            >
              <Send size={16} />
            </button>
          </form>

          <p className="commander-note">
            Responses are deterministic summaries of the local illustrative
            optimizer. No AI service or live mission feed is connected.
          </p>
        </aside>
      </div>
    </main>
  );
}

function Priority({
  label,
  value,
  color,
  onChange,
}: {
  label: string;
  value: number;
  color: string;
  onChange: (value: number) => void;
}) {
  return (
    <label className="priority-control">
      <span>
        {label}
        <strong>{value}%</strong>
      </span>
      <input
        className={color}
        type="range"
        min="0"
        max="100"
        value={value}
        onChange={(event) => onChange(Number(event.currentTarget.value))}
      />
    </label>
  );
}

export default App;
