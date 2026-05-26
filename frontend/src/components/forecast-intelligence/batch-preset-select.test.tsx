import { afterEach, describe, expect, it } from 'vitest'
import { cleanup } from '@testing-library/react'
import {
  BATCH_PRESETS,
  buildPresetConfigs,
} from './batch-preset-utils'

afterEach(cleanup)

describe('BATCH_PRESETS', () => {
  it('exposes 5 presets', () => {
    expect(BATCH_PRESETS.length).toBe(5)
  })
})

describe('buildPresetConfigs', () => {
  it('quick_baseline_sweep emits 5 baseline rows with no feature_frame_version', () => {
    const rows = buildPresetConfigs('quick_baseline_sweep')
    expect(rows.length).toBe(5)
    for (const row of rows) {
      expect(row.feature_frame_version).toBeUndefined()
      expect(row.feature_groups).toBeUndefined()
    }
  })

  it('feature_aware_comparison emits V2 + default groups rows', () => {
    const rows = buildPresetConfigs('feature_aware_comparison')
    expect(rows.length).toBe(5)
    for (const row of rows) {
      expect(row.feature_frame_version).toBe(2)
      expect(row.feature_groups).toContain('target_history')
      expect(row.feature_groups).toContain('lifecycle')
    }
  })

  it('stockout_sensitive_products emits a single regression V2 row with inventory + replenishment + returns', () => {
    const rows = buildPresetConfigs('stockout_sensitive_products')
    expect(rows.length).toBe(1)
    const row = rows[0]!
    expect(row.model_type).toBe('regression')
    expect(row.feature_frame_version).toBe(2)
    expect(row.feature_groups).toContain('inventory')
    expect(row.feature_groups).toContain('replenishment')
    expect(row.feature_groups).toContain('returns')
  })

  it('champion_challenger_refresh emits champion + distinct challenger when both supplied', () => {
    const rows = buildPresetConfigs('champion_challenger_refresh', {
      championModelType: 'lightgbm',
      challengerModelType: 'xgboost',
    })
    expect(rows.length).toBe(2)
    expect(rows[0]?.model_type).toBe('lightgbm')
    expect(rows[1]?.model_type).toBe('xgboost')
  })

  it('champion_challenger_refresh dedupes when challenger matches champion', () => {
    const rows = buildPresetConfigs('champion_challenger_refresh', {
      championModelType: 'lightgbm',
      challengerModelType: 'lightgbm',
    })
    expect(rows.length).toBe(1)
  })

  it('champion_challenger_refresh falls back to naive + lightgbm when no champion supplied', () => {
    const rows = buildPresetConfigs('champion_challenger_refresh')
    expect(rows.length).toBe(2)
    expect(rows[0]?.model_type).toBe('naive')
    expect(rows[1]?.model_type).toBe('lightgbm')
  })
})
