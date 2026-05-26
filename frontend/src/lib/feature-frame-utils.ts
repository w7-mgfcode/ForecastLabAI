/**
 * PRP-37 Slice C — Feature-frame helpers.
 *
 * Defensive client-side mirror of the PRP-35 V2 contract that lives in
 * `app/shared/feature_frames/contract_v2.py`. Anything declared here is
 * VERIFIED against that file via the Task 1 contract probe; the runtime
 * source of truth is the backend response (FeatureMetadataResponse). When
 * the two disagree, trust the backend and fix this file.
 */

import type {
  FeatureFrameVersion,
  FeatureGroup,
  FeatureMetadataResponse,
  FeatureSafetyClass,
} from '@/types/api'

/** UI-facing labels — sourced from PRP-35 §"V2 feature contract". */
const GROUP_LABELS: Record<FeatureGroup, string> = {
  target_history: 'Target history (lags + same-DOW mean)',
  rolling: 'Rolling means',
  trend: 'Trend (30 / 90-day)',
  calendar: 'Calendar (DOW, month, sin / cos)',
  price_promo: 'Price + promotion',
  inventory: 'Inventory + stockout',
  lifecycle: 'Product lifecycle',
  replenishment: 'Replenishment cadence',
  returns: 'Returns intensity',
  exogenous_weather: 'Weather signals',
  exogenous_macro: 'Macro signals',
}

/** Concise label for a {@link FeatureGroup} — for dense UI surfaces. */
export function labelForGroup(group: FeatureGroup): string {
  return GROUP_LABELS[group]
}

/** Map a safety class to the badge variant the UI renders. */
export function safetyClassChipVariant(
  safety: FeatureSafetyClass,
): 'success' | 'warning' | 'error' {
  switch (safety) {
    case 'safe':
      return 'success'
    case 'conditionally_safe':
      return 'warning'
    case 'unsafe_unless_supplied':
      return 'error'
  }
}

/** Human-readable label for a safety class. */
export function labelForSafetyClass(safety: FeatureSafetyClass): string {
  switch (safety) {
    case 'safe':
      return 'Safe'
    case 'conditionally_safe':
      return 'Conditionally safe'
    case 'unsafe_unless_supplied':
      return 'Requires supplied data'
  }
}

/**
 * V2 is available iff the backend feature-metadata response reports
 * `feature_frame_version === 2` OR a non-empty `feature_groups` dict.
 * Either signal independently proves the server shipped Forecast
 * Intelligence A (PRP-35); we treat the OR conservatively so a pre-PRP-35
 * server (no fields at all) renders the V2 control disabled.
 */
export function isV2Available(
  meta: FeatureMetadataResponse | undefined,
): boolean {
  if (!meta) return false
  if (meta.feature_frame_version === 2) return true
  if (
    meta.feature_groups &&
    Object.keys(meta.feature_groups).length > 0
  ) {
    return true
  }
  return false
}

/**
 * Mirror of `app/shared/feature_frames/contract_v2.py:DEFAULT_V2_GROUPS`.
 * Used by the "use defaults" affordance on the feature-groups toggle and
 * by the batch-preset builder. Task 1 verifies value-by-value.
 */
export function defaultV2Groups(): FeatureGroup[] {
  return [
    'target_history',
    'calendar',
    'rolling',
    'trend',
    'price_promo',
    'lifecycle',
  ]
}

/** Human-readable label for a frame version. */
export function labelForVersion(v: FeatureFrameVersion): string {
  return v === 2 ? 'V2 — feature-aware' : 'V1 — target-only'
}
