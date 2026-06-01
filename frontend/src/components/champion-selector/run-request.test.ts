import { describe, expect, it } from 'vitest'
import { assembleRunRequest } from './run-request'
import type { SplitConfig } from '@/types/api'

const SPLIT: SplitConfig = {
  strategy: 'expanding',
  n_splits: 5,
  min_train_size: 30,
  gap: 0,
  horizon: 7, // intentionally stale — must be overridden to forecastHorizon
}

describe('assembleRunRequest', () => {
  it('pins auto_train_winner and auto_predict to false (Slice A invariant)', () => {
    const req = assembleRunRequest({
      storeId: 7,
      productId: 12,
      startDate: '2026-01-01',
      endDate: '2026-05-31',
      forecastHorizon: 14,
      rankingMetric: 'wape',
      splitConfig: SPLIT,
      selectedModels: ['naive', 'regression'],
    })
    expect(req.auto_train_winner).toBe(false)
    expect(req.auto_predict).toBe(false)
  })

  it('forces split_config.horizon === forecast_horizon', () => {
    const req = assembleRunRequest({
      storeId: 1,
      productId: 2,
      startDate: '2026-01-01',
      endDate: '2026-03-31',
      forecastHorizon: 21,
      rankingMetric: 'wape',
      splitConfig: SPLIT,
      selectedModels: ['naive'],
    })
    expect(req.forecast_horizon).toBe(21)
    expect(req.split_config.horizon).toBe(21)
  })

  it('maps selected model types into flat candidate configs and stays V1', () => {
    const req = assembleRunRequest({
      storeId: 1,
      productId: 2,
      startDate: '2026-01-01',
      endDate: '2026-03-31',
      forecastHorizon: 14,
      rankingMetric: 'smape',
      splitConfig: SPLIT,
      selectedModels: ['naive', 'seasonal_naive'],
    })
    expect(req.candidate_models).toEqual([
      { model_type: 'naive', params: {} },
      { model_type: 'seasonal_naive', params: {} },
    ])
    expect(req.feature_frame_version).toBe(1)
    expect(req.feature_groups).toBeNull()
    expect(req.ranking_metric).toBe('smape')
  })
})
