import { describe, expect, it } from 'vitest'
import {
  DEFAULT_BACKTEST,
  DEFAULT_TRAIN_MODELS,
  buildTrainPlan,
  isDefaultBacktest,
  isDefaultSelection,
  parseRunConfig,
  splitFitWarning,
  windowDaysFor,
} from './run-config-utils'
import type { DemoBacktestConfig } from '@/types/api'

describe('isDefaultSelection', () => {
  it('is true for the default trio regardless of order', () => {
    expect(isDefaultSelection([...DEFAULT_TRAIN_MODELS])).toBe(true)
    expect(isDefaultSelection(['moving_average', 'naive', 'seasonal_naive'])).toBe(true)
  })

  it('is false for any other selection', () => {
    expect(isDefaultSelection(['naive'])).toBe(false)
    expect(isDefaultSelection(['naive', 'seasonal_naive', 'regression'])).toBe(false)
  })
})

describe('isDefaultBacktest', () => {
  it('is true for the default config', () => {
    expect(isDefaultBacktest({ ...DEFAULT_BACKTEST })).toBe(true)
  })

  it('is false when any knob differs', () => {
    expect(isDefaultBacktest({ ...DEFAULT_BACKTEST, metric: 'rmse' })).toBe(false)
    expect(isDefaultBacktest({ ...DEFAULT_BACKTEST, horizon: 21 })).toBe(false)
  })
})

describe('buildTrainPlan', () => {
  it('returns the selection verbatim on non-showcase scenarios', () => {
    const plan = buildTrainPlan(['naive', 'seasonal_average'], 'demo_minimal')
    expect(plan.map((p) => p.model_type)).toEqual(['naive', 'seasonal_average'])
    expect(plan.some((p) => p.v2)).toBe(false)
  })

  it('appends prophet_like (V2) on showcase_rich when absent', () => {
    const plan = buildTrainPlan(['naive'], 'showcase_rich')
    expect(plan.map((p) => p.model_type)).toEqual(['naive', 'prophet_like'])
    expect(plan[1].v2).toBe(true)
  })

  it('does not double-append prophet_like when already selected', () => {
    const plan = buildTrainPlan(['prophet_like', 'naive'], 'showcase_rich')
    expect(plan.map((p) => p.model_type)).toEqual(['prophet_like', 'naive'])
  })

  it('tags each chip with its family from the catalog map', () => {
    const plan = buildTrainPlan(['naive'], 'demo_minimal', { naive: 'baseline' })
    expect(plan[0].family).toBe('baseline')
  })
})

describe('windowDaysFor', () => {
  it('returns 92 for the short-window presets', () => {
    expect(windowDaysFor('demo_minimal')).toBe(92)
    expect(windowDaysFor('sparse')).toBe(92)
    expect(windowDaysFor('holiday_rush')).toBe(92)
  })

  it('returns 180 for the rich-window presets', () => {
    expect(windowDaysFor('showcase_rich')).toBe(180)
    expect(windowDaysFor('retail_standard')).toBe(180)
  })
})

describe('splitFitWarning', () => {
  it('returns null when the split fits the window', () => {
    expect(splitFitWarning({ ...DEFAULT_BACKTEST }, 'demo_minimal')).toBeNull()
  })

  it('warns when the split exceeds the seeded window', () => {
    const aggressive: DemoBacktestConfig = {
      ...DEFAULT_BACKTEST,
      horizon: 28,
      n_splits: 5,
      min_train_size: 60,
    }
    const warning = splitFitWarning(aggressive, 'demo_minimal')
    expect(warning).toContain('demo_minimal')
  })
})

describe('parseRunConfig', () => {
  it('returns null for a null/empty config', () => {
    expect(parseRunConfig(null)).toBeNull()
    expect(parseRunConfig(undefined)).toBeNull()
  })

  it('parses train_model_types + backtest, defaulting missing knobs', () => {
    const parsed = parseRunConfig({
      train_model_types: ['naive', 'regression'],
      backtest: { horizon: 21, metric: 'rmse' },
    })
    expect(parsed).not.toBeNull()
    expect(parsed!.trainModels).toEqual(['naive', 'regression'])
    expect(parsed!.backtest.horizon).toBe(21)
    expect(parsed!.backtest.metric).toBe('rmse')
    // Missing knobs fall back to the defaults.
    expect(parsed!.backtest.n_splits).toBe(DEFAULT_BACKTEST.n_splits)
    expect(parsed!.backtest.strategy).toBe(DEFAULT_BACKTEST.strategy)
  })

  it('falls back to the default trio when models are malformed', () => {
    const parsed = parseRunConfig({ train_model_types: 'oops', backtest: {} })
    expect(parsed!.trainModels).toEqual(DEFAULT_TRAIN_MODELS)
  })
})
