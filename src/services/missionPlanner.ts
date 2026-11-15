export const missionObjectives = [
  "Search for Ancient Hydrous Minerals",
  "Map Subsurface Water Ice",
  "Assess Geological Traversability",
] as const;

export type MissionObjective = (typeof missionObjectives)[number];

export type RouteCandidate = {
  id: string;
  name: string;
  distance: number;
  duration: number;
  oxygen: number;
  maxSlope: number;
  hazard: number;
  color: string;
  scienceByObjective: Record<MissionObjective, number>;
};

export type MissionConstraints = {
  maxDuration: number;
  minOxygen: number;
  maxSlope: number;
};

export type MissionPriorities = {
  science: number;
  safety: number;
  time: number;
  energy: number;
};

export type RouteAssessment = RouteCandidate & {
  feasible: boolean;
  failures: string[];
  score: number;
  scienceScore: number;
  safetyScore: number;
  timeScore: number;
  energyScore: number;
};

export const demoRouteCandidates: RouteCandidate[] = [
  {
    id: "alpha",
    name: "Route Alpha",
    distance: 5.8,
    duration: 5.2,
    oxygen: 38,
    maxSlope: 11.4,
    hazard: 0.31,
    color: "#f2aa22",
    scienceByObjective: {
      "Search for Ancient Hydrous Minerals": 94,
      "Map Subsurface Water Ice": 70,
      "Assess Geological Traversability": 68,
    },
  },
  {
    id: "bravo",
    name: "Route Bravo",
    distance: 6.4,
    duration: 4.9,
    oxygen: 44,
    maxSlope: 12.8,
    hazard: 0.28,
    color: "#60a5fa",
    scienceByObjective: {
      "Search for Ancient Hydrous Minerals": 82,
      "Map Subsurface Water Ice": 94,
      "Assess Geological Traversability": 72,
    },
  },
  {
    id: "charlie",
    name: "Route Charlie",
    distance: 4.8,
    duration: 3.1,
    oxygen: 41,
    maxSlope: 15.6,
    hazard: 0.38,
    color: "#34d399",
    scienceByObjective: {
      "Search for Ancient Hydrous Minerals": 65,
      "Map Subsurface Water Ice": 77,
      "Assess Geological Traversability": 94,
    },
  },
];

const clampScore = (score: number) => Math.max(0, Math.min(100, score));

export function assessRoutes(
  candidates: RouteCandidate[],
  constraints: MissionConstraints,
  priorities: MissionPriorities,
  objective: MissionObjective,
): RouteAssessment[] {
  const priorityTotal =
    priorities.science +
    priorities.safety +
    priorities.time +
    priorities.energy;
  const weights =
    priorityTotal === 0
      ? { science: 25, safety: 25, time: 25, energy: 25 }
      : {
          science: (priorities.science / priorityTotal) * 100,
          safety: (priorities.safety / priorityTotal) * 100,
          time: (priorities.time / priorityTotal) * 100,
          energy: (priorities.energy / priorityTotal) * 100,
        };

  return candidates
    .map((route) => {
      const failures: string[] = [];
      if (route.duration > constraints.maxDuration) {
        failures.push(
          `duration ${route.duration} h exceeds ${constraints.maxDuration} h limit`,
        );
      }
      if (route.oxygen < constraints.minOxygen) {
        failures.push(
          `oxygen reserve ${route.oxygen}% is below ${constraints.minOxygen}% minimum`,
        );
      }
      if (route.maxSlope > constraints.maxSlope) {
        failures.push(
          `route slope ${route.maxSlope}° exceeds ${constraints.maxSlope}° limit`,
        );
      }

      const scienceScore = route.scienceByObjective[objective];
      const safetyScore = clampScore(
        (100 - route.hazard * 100 + route.oxygen + (100 - route.maxSlope * 2.5)) /
          3,
      );
      const timeScore = clampScore(100 - (route.duration / 12) * 100);
      const energyScore = clampScore(
        100 - route.distance * 5 - route.maxSlope * 1.1 - route.duration,
      );
      const score =
        (scienceScore * weights.science +
          safetyScore * weights.safety +
          timeScore * weights.time +
          energyScore * weights.energy) /
        100;

      return {
        ...route,
        feasible: failures.length === 0,
        failures,
        score,
        scienceScore,
        safetyScore,
        timeScore,
        energyScore,
      };
    })
    .sort((first, second) => {
      if (first.feasible !== second.feasible) {
        return first.feasible ? -1 : 1;
      }
      return second.score - first.score;
    });
}
