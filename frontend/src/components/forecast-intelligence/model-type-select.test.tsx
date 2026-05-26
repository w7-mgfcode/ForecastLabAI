import { afterEach, describe, expect, it } from 'vitest'
import { cleanup } from '@testing-library/react'
import {
  MODEL_FAMILY_MAP,
  MODEL_TYPE_LABELS,
  modelsForFamily,
} from './model-type-utils'

afterEach(cleanup)

describe('MODEL_FAMILY_MAP', () => {
  it('includes the 5 baseline model types (naive + 4 others)', () => {
    expect(MODEL_FAMILY_MAP.baseline).toEqual([
      'naive',
      'seasonal_naive',
      'moving_average',
      'weighted_moving_average',
      'seasonal_average',
    ])
  })

  it('includes the 4 tree model types', () => {
    expect(MODEL_FAMILY_MAP.tree).toEqual([
      'regression',
      'lightgbm',
      'xgboost',
      'random_forest',
    ])
  })

  it('includes the 2 additive model types', () => {
    expect(MODEL_FAMILY_MAP.additive).toEqual([
      'prophet_like',
      'trend_regression_baseline',
    ])
  })
})

describe('MODEL_TYPE_LABELS', () => {
  it('labels every model type listed in MODEL_FAMILY_MAP', () => {
    const allTypes = [
      ...MODEL_FAMILY_MAP.baseline,
      ...MODEL_FAMILY_MAP.tree,
      ...MODEL_FAMILY_MAP.additive,
    ]
    for (const modelType of allTypes) {
      expect(MODEL_TYPE_LABELS[modelType]).toBeTruthy()
    }
  })
})

describe('modelsForFamily', () => {
  it('returns every model in the family when no restriction is supplied', () => {
    expect(modelsForFamily('tree')).toEqual(MODEL_FAMILY_MAP.tree)
  })

  it('filters by the availableModels intersection', () => {
    expect(modelsForFamily('tree', ['lightgbm', 'xgboost', 'naive'])).toEqual([
      'lightgbm',
      'xgboost',
    ])
  })

  it('returns an empty array when the family has no overlap with availableModels', () => {
    expect(modelsForFamily('additive', ['naive'])).toEqual([])
  })
})
