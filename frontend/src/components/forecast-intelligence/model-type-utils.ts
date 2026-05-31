/**
 * PRP-37 Slice C — shared model-type metadata. Split from
 * `model-type-select.tsx` so the react-refresh lint rule (only-export-components)
 * stays clean for the .tsx surface.
 */

import type { ModelFamily } from '@/types/api'

export const MODEL_FAMILY_MAP: Record<ModelFamily, string[]> = {
  baseline: [
    'naive',
    'seasonal_naive',
    'moving_average',
    'weighted_moving_average',
    'seasonal_average',
  ],
  tree: ['regression', 'lightgbm', 'xgboost', 'random_forest'],
  additive: ['prophet_like', 'trend_regression_baseline'],
}

export const MODEL_TYPE_LABELS: Record<string, string> = {
  naive: 'Naive',
  seasonal_naive: 'Seasonal Naive',
  moving_average: 'Moving Average',
  weighted_moving_average: 'Weighted Moving Average',
  seasonal_average: 'Seasonal Average',
  regression: 'Regression (HistGBR)',
  lightgbm: 'LightGBM',
  xgboost: 'XGBoost',
  random_forest: 'Random Forest',
  prophet_like: 'Prophet-like (Ridge additive)',
  trend_regression_baseline: 'Trend Regression Baseline',
}

export function modelsForFamily(
  family: ModelFamily,
  availableModels?: string[],
): string[] {
  const all = MODEL_FAMILY_MAP[family]
  if (!availableModels) return all
  return all.filter((m) => availableModels.includes(m))
}
