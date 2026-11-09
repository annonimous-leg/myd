/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

// =============================================================================
// Megalodon CostOS — Monte Carlo Risk Simulation Engine
// =============================================================================

export interface SimulationVariable {
  name: string;
  mean: number;
  stdDev: number;
  distribution: 'normal' | 'triangular' | 'uniform';
  min?: number;
  max?: number;
}

export interface SimulationConfig {
  iterations: number;
  confidenceLevel: number;
  variables: SimulationVariable[];
}

export interface SimulationResult {
  /** Mean of all simulated totals */
  mean: number;
  /** Median (P50) */
  median: number;
  /** Standard deviation */
  stdDev: number;
  /** P1 percentile */
  p1: number;
  /** P5 percentile */
  p5: number;
  /** P10 percentile */
  p10: number;
  /** P25 percentile */
  p25: number;
  /** P50 percentile (median) */
  p50: number;
  /** P75 percentile */
  p75: number;
  /** P90 percentile */
  p90: number;
  /** P95 percentile */
  p95: number;
  /** P99 percentile */
  p99: number;
  /** Coefficient of variation (%) */
  cv: number;
  /** Requested confidence interval for the simulation mean */
  confidenceLevel?: number;
  confidenceInterval?: [number, number];
  /** Cost exceedance probability at the configured budget threshold */
  probabilityBudgetExceedance?: number | null;
  /** Schedule risk, when simulated */
  schedule?: {
    p50: number;
    p80: number;
    p90: number;
    p95: number;
    probabilityExceedance?: number | null;
  };
  /** Histogram bins */
  histogram: HistogramBin[];
  /** Per-variable sensitivity (tornado chart data) */
  sensitivity: SensitivityItem[];
}

export interface HistogramBin {
  min: number;
  max: number;
  count: number;
  frequency: number;
}

export interface SensitivityItem {
  variable: string;
  impact: number;
  lowValue: number;
  highValue: number;
}

/** Box-Muller transform for normal distribution sampling */
function normalRandom(mean: number, stdDev: number): number {
  let u = 0, v = 0;
  while (u === 0) u = Math.random();
  while (v === 0) v = Math.random();
  const z = Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
  return mean + z * stdDev;
}

/** Sample from triangular distribution */
function triangularRandom(min: number, max: number, mode: number): number {
  const u = Math.random();
  const f = (mode - min) / (max - min);
  if (u <= f) {
    return min + Math.sqrt(u * (max - min) * (mode - min));
  }
  return max - Math.sqrt((1 - u) * (max - min) * (max - mode));
}

/** Sample from uniform distribution */
function uniformRandom(min: number, max: number): number {
  return min + Math.random() * (max - min);
}

/** Sample a single value from a variable's distribution */
function sampleVariable(v: SimulationVariable): number {
  let value: number;
  switch (v.distribution) {
    case 'triangular':
      value = triangularRandom(v.min ?? v.mean - v.stdDev * 2, v.max ?? v.mean + v.stdDev * 2, v.mean);
      break;
    case 'uniform':
      value = uniformRandom(v.min ?? v.mean - v.stdDev * 2, v.max ?? v.mean + v.stdDev * 2);
      break;
    case 'normal':
    default:
      value = normalRandom(v.mean, v.stdDev);
      break;
  }
  // Ensure non-negative for cost variables
  return Math.max(0, value);
}

/** Run Monte Carlo simulation */
export function runMonteCarlo(config: SimulationConfig): SimulationResult {
  const { iterations, variables } = config;
  const totals: number[] = new Array(iterations);

  // Main simulation loop
  for (let i = 0; i < iterations; i++) {
    let total = 0;
    for (const v of variables) {
      total += sampleVariable(v);
    }
    totals[i] = total;
  }

  // Sort for percentile calculations
  totals.sort((a, b) => a - b);

  const mean = totals.reduce((s, v) => s + v, 0) / iterations;

  // Standard deviation
  const variance = totals.reduce((s, v) => s + (v - mean) ** 2, 0) / iterations;
  const stdDev = Math.sqrt(variance);

  // Percentiles
  const percentile = (p: number) => {
    const idx = Math.floor((p / 100) * (totals.length - 1));
    return totals[Math.max(0, Math.min(idx, totals.length - 1))];
  };

  const p50 = percentile(50);

  // Build histogram (30 bins)
  const minVal = totals[0];
  const maxVal = totals[totals.length - 1];
  const binWidth = (maxVal - minVal) / 30 || 1;
  const histogram: HistogramBin[] = [];

  for (let b = 0; b < 30; b++) {
    const binMin = minVal + b * binWidth;
    const binMax = binMin + binWidth;
    const count = totals.filter((v) => v >= binMin && v < binMax).length;
    histogram.push({
      min: binMin,
      max: binMax,
      count,
      frequency: count / iterations,
    });
  }

  // Sensitivity analysis (tornado chart)
  // Measure impact of each variable by running partial simulations
  const sensitivity: SensitivityItem[] = variables.map((v) => {
    // Low scenario: this variable at P10, others at mean
    const lowMean = v.mean - 1.282 * v.stdDev; // ~P10 for normal
    const highMean = v.mean + 1.282 * v.stdDev; // ~P90

    let lowTotal = 0;
    let highTotal = 0;
    const sampleCount = Math.min(200, iterations);

    for (let i = 0; i < sampleCount; i++) {
      let lowSum = 0;
      let highSum = 0;
      for (const ov of variables) {
        if (ov.name === v.name) {
          lowSum += Math.max(0, normalRandom(lowMean, ov.stdDev * 0.3));
          highSum += Math.max(0, normalRandom(highMean, ov.stdDev * 0.3));
        } else {
          const sample = sampleVariable(ov);
          lowSum += sample;
          highSum += sample;
        }
      }
      lowTotal += lowSum;
      highTotal += highSum;
    }

    const lowAvg = lowTotal / sampleCount;
    const highAvg = highTotal / sampleCount;

    return {
      variable: v.name,
      impact: Math.abs(highAvg - lowAvg),
      lowValue: lowAvg,
      highValue: highAvg,
    };
  });

  // Sort sensitivity by impact descending
  sensitivity.sort((a, b) => b.impact - a.impact);

  return {
    mean,
    median: p50,
    stdDev,
    p1: percentile(1),
    p5: percentile(5),
    p10: percentile(10),
    p25: percentile(25),
    p50,
    p75: percentile(75),
    p90: percentile(90),
    p95: percentile(95),
    p99: percentile(99),
    cv: (stdDev / mean) * 100,
    histogram,
    sensitivity,
  };
}

/** Format currency as MXN */
export function formatMXN(value: number): string {
  return `$${value.toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** Generate default simulation variables for a construction project */
export function getDefaultSimulationVariables(): SimulationVariable[] {
  return [
    { name: 'Materiales de concreto', mean: 2_847_500, stdDev: 185_000, distribution: 'normal' },
    { name: 'Acero de refuerzo', mean: 1_250_000, stdDev: 95_000, distribution: 'normal' },
    { name: 'Mampostería', mean: 485_000, stdDev: 42_000, distribution: 'normal' },
    { name: 'Mano de obra directa', mean: 3_200_000, stdDev: 280_000, distribution: 'normal' },
    { name: 'Maquinaria y equipo', mean: 950_000, stdDev: 125_000, distribution: 'normal' },
    { name: 'Instalaciones especiales', mean: 625_000, stdDev: 55_000, distribution: 'normal' },
    { name: 'Acabados', mean: 1_100_000, stdDev: 88_000, distribution: 'normal' },
    { name: 'Gastos indirectos', mean: 1_450_000, stdDev: 72_000, distribution: 'normal' },
    { name: 'Financiamiento', mean: 485_000, stdDev: 35_000, distribution: 'normal' },
    { name: 'Contingencia', mean: 750_000, stdDev: 120_000, distribution: 'normal' },
  ];
}
