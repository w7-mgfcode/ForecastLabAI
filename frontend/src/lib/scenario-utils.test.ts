import { describe, expect, it } from 'vitest'
import {
  buildMultiSeries,
  coverageLabel,
  coverageVariant,
  formatDelta,
  mergeComparisonSeries,
  methodLabel,
  summariseAssumptions,
} from './scenario-utils'
import type {
  MultiScenarioComparison,
  ScenarioAssumptions,
  ScenarioComparisonRow,
  ScenarioPoint,
} from '@/types/api'

function makePoint(date: string, baseline: number, scenario: number): ScenarioPoint {
  return {
    date,
    baseline,
    scenario,
    delta: scenario - baseline,
    applied_factor: baseline === 0 ? 1 : scenario / baseline,
  }
}

describe('mergeComparisonSeries', () => {
  it('flattens points into date / baseline / scenario rows', () => {
    const rows = mergeComparisonSeries([makePoint('2026-07-01', 10, 12)])
    expect(rows).toEqual([{ date: '2026-07-01', baseline: 10, scenario: 12 }])
  })

  it('returns an empty array for no points', () => {
    expect(mergeComparisonSeries([])).toEqual([])
  })
})

describe('formatDelta', () => {
  it('prefixes a plus sign for positive values', () => {
    expect(formatDelta(12.34)).toBe('+12.3')
  })

  it('keeps the minus sign for negative values', () => {
    expect(formatDelta(-4.5)).toBe('-4.5')
  })

  it('formats zero without a sign', () => {
    expect(formatDelta(0)).toBe('0.0')
  })

  it('honours the decimals argument', () => {
    expect(formatDelta(3, 0)).toBe('+3')
  })
})

describe('coverageLabel / coverageVariant', () => {
  it('maps every verdict to a label and a badge variant', () => {
    expect(coverageLabel('covered')).toBe('Covered')
    expect(coverageLabel('at_risk')).toBe('At risk')
    expect(coverageLabel('stockout')).toBe('Stockout')
    expect(coverageLabel('unknown')).toBe('Unknown')
    expect(coverageVariant('covered')).toBe('success')
    expect(coverageVariant('at_risk')).toBe('warning')
    expect(coverageVariant('stockout')).toBe('error')
    expect(coverageVariant('unknown')).toBe('default')
  })
})

describe('summariseAssumptions', () => {
  it('returns a baseline-only line for empty assumptions', () => {
    expect(summariseAssumptions({})).toEqual(['No assumptions — baseline only'])
  })

  it('summarises a price cut with sign-aware wording', () => {
    const assumptions: ScenarioAssumptions = {
      price: { change_pct: -0.15, start_date: '2026-07-01', end_date: '2026-07-14' },
    }
    const [line] = summariseAssumptions(assumptions)
    expect(line).toContain('Price cut of 15%')
  })

  it('lists every supplied assumption', () => {
    const assumptions: ScenarioAssumptions = {
      price: { change_pct: 0.1, start_date: '2026-07-01', end_date: '2026-07-07' },
      promotion: { kind: 'bogo', start_date: '2026-07-02', end_date: '2026-07-05' },
      holiday: { dates: ['2026-07-04'] },
      inventory: { on_hand_units: 500 },
      lifecycle: { stage: 'growth' },
    }
    const lines = summariseAssumptions(assumptions)
    expect(lines).toHaveLength(5)
    expect(lines[0]).toContain('Price increase of 10%')
    expect(lines[1]).toContain('bogo promotion')
    expect(lines[2]).toContain('1 holiday/event day')
    expect(lines[3]).toContain('500 units')
    expect(lines[4]).toContain('growth')
  })
})

function makeRow(scenarioId: string, name: string, rank: number): ScenarioComparisonRow {
  return {
    scenario_id: scenarioId,
    name,
    units_delta: 0,
    revenue_delta: 0,
    coverage_verdict: 'unknown',
    rank,
  }
}

describe('buildMultiSeries', () => {
  it('puts baseline first, then one line per scenario keyed by scenario_id', () => {
    const comparison: MultiScenarioComparison = {
      baseline_total_units: 100,
      baseline_revenue: 1000,
      rank_by: 'revenue_delta',
      scenarios: [makeRow('sid-a', 'Cut', 1), makeRow('sid-b', 'Rise', 2)],
      chart_series: [],
    }
    expect(buildMultiSeries(comparison)).toEqual([
      { key: 'baseline', label: 'Baseline' },
      { key: 'sid-a', label: 'Cut' },
      { key: 'sid-b', label: 'Rise' },
    ])
  })

  it('returns only the baseline line when there are no scenarios', () => {
    const comparison: MultiScenarioComparison = {
      baseline_total_units: 0,
      baseline_revenue: 0,
      rank_by: 'units_delta',
      scenarios: [],
      chart_series: [],
    }
    expect(buildMultiSeries(comparison)).toEqual([{ key: 'baseline', label: 'Baseline' }])
  })
})

describe('methodLabel', () => {
  it('labels each comparison method', () => {
    expect(methodLabel('heuristic')).toBe('Heuristic')
    expect(methodLabel('model_exogenous')).toBe('Model-driven')
  })
})
