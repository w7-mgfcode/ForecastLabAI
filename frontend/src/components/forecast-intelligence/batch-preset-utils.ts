/**
 * PRP-37 Slice C — shared batch-preset metadata + builder. Split out from
 * the .tsx surface so the react-refresh lint rule stays clean.
 */

import { defaultV2Groups } from '@/lib/feature-frame-utils'
import type { BatchModelConfig, FeatureGroup } from '@/types/api'

export type BatchPresetId =
  | 'quick_baseline_sweep'
  | 'feature_aware_comparison'
  | 'champion_challenger_refresh'
  | 'stockout_sensitive_products'
  | 'high_wape_recovery'

export interface BatchPresetMeta {
  id: BatchPresetId
  label: string
  description: string
}

export const BATCH_PRESETS: BatchPresetMeta[] = [
  {
    id: 'quick_baseline_sweep',
    label: 'Quick baseline sweep',
    description:
      'All five baseline models (naive, seasonal_naive, moving_average, weighted_moving_average, seasonal_average).',
  },
  {
    id: 'feature_aware_comparison',
    label: 'Feature-aware comparison',
    description:
      'Regression, LightGBM, XGBoost, Random Forest, Prophet-like — V2 with default feature packs.',
  },
  {
    id: 'champion_challenger_refresh',
    label: 'Champion/challenger refresh',
    description:
      'The current champion model type + the strongest challenger from the runs explorer; supplied by the page.',
  },
  {
    id: 'stockout_sensitive_products',
    label: 'Stockout-sensitive products',
    description:
      'Regression on V2 with inventory + replenishment + returns packs enabled.',
  },
  {
    id: 'high_wape_recovery',
    label: 'High-WAPE recovery',
    description:
      'Every feature-aware model on V2 with default packs — for grains where baselines are underperforming.',
  },
]

/**
 * Translate a preset id into the `BatchModelConfig[]` the parent submits.
 * `championModelType` + `challengerModelType` are only used by
 * `champion_challenger_refresh`. If a model is server-side gated
 * (lightgbm / xgboost / random_forest), the parent is responsible for
 * filtering the resulting rows against the runtime model allow-list.
 */
export function buildPresetConfigs(
  presetId: BatchPresetId,
  options: {
    championModelType?: string
    challengerModelType?: string
  } = {},
): BatchModelConfig[] {
  const groups: FeatureGroup[] = defaultV2Groups()
  switch (presetId) {
    case 'quick_baseline_sweep':
      return (
        [
          'naive',
          'seasonal_naive',
          'moving_average',
          'weighted_moving_average',
          'seasonal_average',
        ] as const
      ).map((model_type) => ({ model_type }))
    case 'feature_aware_comparison':
      return (
        [
          'regression',
          'lightgbm',
          'xgboost',
          'random_forest',
          'prophet_like',
        ] as const
      ).map((model_type) => ({
        model_type,
        feature_frame_version: 2,
        feature_groups: groups,
      }))
    case 'champion_challenger_refresh': {
      const rows: BatchModelConfig[] = []
      if (options.championModelType) {
        rows.push({ model_type: options.championModelType as never })
      }
      if (
        options.challengerModelType &&
        options.challengerModelType !== options.championModelType
      ) {
        rows.push({ model_type: options.challengerModelType as never })
      }
      // Fallback when callers do not supply a champion: a minimal compare
      // of naive vs lightgbm, the historical "first thing to look at"
      // pair across the registry.
      if (rows.length === 0) {
        rows.push({ model_type: 'naive' }, { model_type: 'lightgbm' })
      }
      return rows
    }
    case 'stockout_sensitive_products':
      return [
        {
          model_type: 'regression',
          feature_frame_version: 2,
          feature_groups: [
            'target_history',
            'calendar',
            'inventory',
            'replenishment',
            'returns',
          ],
        },
      ]
    case 'high_wape_recovery':
      return (
        [
          'regression',
          'lightgbm',
          'xgboost',
          'random_forest',
          'prophet_like',
        ] as const
      ).map((model_type) => ({
        model_type,
        feature_frame_version: 2,
        feature_groups: groups,
      }))
  }
}
