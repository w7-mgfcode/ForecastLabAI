/**
 * Pure helpers for the What-If Planner page.
 *
 * No React, no I/O — every function here is unit-tested in
 * scenario-utils.test.ts. The planner composes these to turn a
 * `ScenarioComparison` into chart rows, a delta table, and readable summaries.
 */
import type { CsvColumn } from '@/lib/csv-export'
import type { CoverageVerdict, ScenarioAssumptions, ScenarioPoint } from '@/types/api'

/** One charted day: a date plus the baseline and scenario demand values. */
export interface ComparisonChartRow {
  date: string
  baseline: number
  scenario: number
  // Index signature so the row is assignable to TimeSeriesChart's data prop.
  [key: string]: string | number | null | undefined
}

/** Flatten comparison points into the two-series rows TimeSeriesChart renders. */
export function mergeComparisonSeries(points: ScenarioPoint[]): ComparisonChartRow[] {
  return points.map((point) => ({
    date: point.date,
    baseline: point.baseline,
    scenario: point.scenario,
  }))
}

/** Format a number with an explicit sign (+1.5 / -2.0 / 0.0). */
export function formatDelta(value: number, decimals = 1): string {
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(decimals)}`
}

/** Human label for a coverage verdict. */
export function coverageLabel(verdict: CoverageVerdict): string {
  switch (verdict) {
    case 'covered':
      return 'Covered'
    case 'at_risk':
      return 'At risk'
    case 'stockout':
      return 'Stockout'
    default:
      return 'Unknown'
  }
}

/** StatusBadge variant for a coverage verdict. */
export function coverageVariant(
  verdict: CoverageVerdict,
): 'success' | 'warning' | 'error' | 'default' {
  switch (verdict) {
    case 'covered':
      return 'success'
    case 'at_risk':
      return 'warning'
    case 'stockout':
      return 'error'
    default:
      return 'default'
  }
}

/** CSV columns for the per-day delta-table export. */
export const deltaCsvColumns: CsvColumn<ScenarioPoint>[] = [
  { key: 'date', header: 'Date' },
  { key: 'baseline', header: 'Baseline' },
  { key: 'scenario', header: 'Scenario' },
  { key: 'delta', header: 'Delta' },
  { key: 'applied_factor', header: 'Factor' },
]

/** Render the active what-if assumptions as human-readable bullet lines. */
export function summariseAssumptions(assumptions: ScenarioAssumptions): string[] {
  const lines: string[] = []

  if (assumptions.price) {
    const pct = Math.round(assumptions.price.change_pct * 100)
    const verb = pct < 0 ? 'cut' : 'increase'
    lines.push(
      `Price ${verb} of ${Math.abs(pct)}% from ${assumptions.price.start_date} ` +
        `to ${assumptions.price.end_date}`,
    )
  }
  if (assumptions.promotion) {
    lines.push(
      `${assumptions.promotion.kind} promotion from ${assumptions.promotion.start_date} ` +
        `to ${assumptions.promotion.end_date}`,
    )
  }
  if (assumptions.holiday && assumptions.holiday.dates.length > 0) {
    const count = assumptions.holiday.dates.length
    lines.push(`${count} holiday/event day${count === 1 ? '' : 's'}`)
  }
  if (assumptions.inventory) {
    lines.push(`On-hand stock of ${assumptions.inventory.on_hand_units} units`)
  }
  if (assumptions.lifecycle) {
    lines.push(`Lifecycle stage forced to "${assumptions.lifecycle.stage}"`)
  }

  if (lines.length === 0) {
    lines.push('No assumptions — baseline only')
  }
  return lines
}
