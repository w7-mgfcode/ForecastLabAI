import { describe, expect, it } from 'vitest'
import {
  defaultV2Groups,
  isV2Available,
  labelForGroup,
  labelForSafetyClass,
  labelForVersion,
  safetyClassChipVariant,
} from './feature-frame-utils'
import type { FeatureMetadataResponse } from '@/types/api'

describe('labelForGroup', () => {
  it('returns the labelled string for every known group', () => {
    expect(labelForGroup('target_history')).toMatch(/target history/i)
    expect(labelForGroup('rolling')).toMatch(/rolling/i)
    expect(labelForGroup('calendar')).toMatch(/calendar/i)
    expect(labelForGroup('price_promo')).toMatch(/price/i)
    expect(labelForGroup('inventory')).toMatch(/inventory/i)
    expect(labelForGroup('lifecycle')).toMatch(/lifecycle/i)
    expect(labelForGroup('replenishment')).toMatch(/replenishment/i)
    expect(labelForGroup('returns')).toMatch(/returns/i)
    expect(labelForGroup('exogenous_weather')).toMatch(/weather/i)
    expect(labelForGroup('exogenous_macro')).toMatch(/macro/i)
    expect(labelForGroup('trend')).toMatch(/trend/i)
  })
})

describe('safetyClassChipVariant', () => {
  it('maps safe → success', () => {
    expect(safetyClassChipVariant('safe')).toBe('success')
  })

  it('maps conditionally_safe → warning', () => {
    expect(safetyClassChipVariant('conditionally_safe')).toBe('warning')
  })

  it('maps unsafe_unless_supplied → error', () => {
    expect(safetyClassChipVariant('unsafe_unless_supplied')).toBe('error')
  })
})

describe('labelForSafetyClass', () => {
  it('returns a human-readable label for each class', () => {
    expect(labelForSafetyClass('safe')).toBe('Safe')
    expect(labelForSafetyClass('conditionally_safe')).toMatch(/conditional/i)
    expect(labelForSafetyClass('unsafe_unless_supplied')).toMatch(/supplied/i)
  })
})

describe('isV2Available', () => {
  it('returns false for undefined metadata', () => {
    expect(isV2Available(undefined)).toBe(false)
  })

  it('returns true when feature_frame_version is 2', () => {
    const meta: FeatureMetadataResponse = {
      run_id: 'r',
      model_type: 'lightgbm',
      model_family: 'tree',
      feature_columns: [],
      features: [],
      importance_type: null,
      feature_frame_version: 2,
    }
    expect(isV2Available(meta)).toBe(true)
  })

  it('returns true when feature_groups is a non-empty dict (V1 sentinel)', () => {
    const meta: FeatureMetadataResponse = {
      run_id: 'r',
      model_type: 'regression',
      model_family: 'additive',
      feature_columns: [],
      features: [],
      importance_type: null,
      feature_groups: { target_history: ['lag_1'] },
    }
    expect(isV2Available(meta)).toBe(true)
  })

  it('returns false when feature_groups is empty and version is 1', () => {
    const meta: FeatureMetadataResponse = {
      run_id: 'r',
      model_type: 'naive',
      model_family: 'baseline',
      feature_columns: [],
      features: [],
      importance_type: null,
      feature_frame_version: 1,
      feature_groups: {},
    }
    expect(isV2Available(meta)).toBe(false)
  })

  it('returns false when neither field is set', () => {
    const meta: FeatureMetadataResponse = {
      run_id: 'r',
      model_type: 'naive',
      model_family: 'baseline',
      feature_columns: [],
      features: [],
      importance_type: null,
    }
    expect(isV2Available(meta)).toBe(false)
  })
})

describe('defaultV2Groups', () => {
  it('returns the 6 groups mirroring app/shared/feature_frames/contract_v2.py:DEFAULT_V2_GROUPS', () => {
    expect(defaultV2Groups()).toEqual([
      'target_history',
      'calendar',
      'rolling',
      'trend',
      'price_promo',
      'lifecycle',
    ])
  })
})

describe('labelForVersion', () => {
  it('labels V1 / V2 distinctly', () => {
    expect(labelForVersion(1)).toMatch(/V1/i)
    expect(labelForVersion(2)).toMatch(/V2/i)
  })
})
