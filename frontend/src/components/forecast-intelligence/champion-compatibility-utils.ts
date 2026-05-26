/**
 * PRP-37 Slice C — comparable-run rule, factored out from the badge .tsx
 * so the react-refresh lint rule stays clean and the rule is independently
 * importable by future surfaces (e.g. the Ops page).
 */

import type { FeatureFrameVersion, ModelRun } from '@/types/api'

export interface CompatibilityResult {
  ok: boolean
  reason?: string
}

export function computeCompatibility(
  a: ModelRun,
  b: ModelRun,
): CompatibilityResult {
  if (a.store_id !== b.store_id || a.product_id !== b.product_id) {
    return { ok: false, reason: 'Different grain (store + product)' }
  }
  const a_start = new Date(a.data_window_start).getTime()
  const a_end = new Date(a.data_window_end).getTime()
  const b_start = new Date(b.data_window_start).getTime()
  const b_end = new Date(b.data_window_end).getTime()
  // Treat NaN (unparseable date) as a non-overlap to be safe — operators
  // would rather see "not comparable" than a silent overlap match.
  if (
    !Number.isFinite(a_start) ||
    !Number.isFinite(a_end) ||
    !Number.isFinite(b_start) ||
    !Number.isFinite(b_end)
  ) {
    return { ok: false, reason: 'Unparseable data-window dates' }
  }
  if (a_end < b_start || b_end < a_start) {
    return { ok: false, reason: 'No data-window overlap' }
  }
  const va: FeatureFrameVersion = a.feature_frame_version === 2 ? 2 : 1
  const vb: FeatureFrameVersion = b.feature_frame_version === 2 ? 2 : 1
  if (va !== vb) {
    return {
      ok: false,
      reason: `Different feature frame version (V${va} vs V${vb})`,
    }
  }
  return { ok: true }
}
