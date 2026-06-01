/**
 * Non-component constants for the Slice C decision panels. Kept in a `.ts`
 * module so `react-refresh/only-export-components` never trips on them.
 */

/** Service levels the safety-stock z-table supports exactly (others snap nearest). */
export const SERVICE_LEVEL_OPTIONS = [0.9, 0.95, 0.975, 0.99] as const

/** Capability-limited blocked state for a feature-aware winner (LOCKED #5). */
export const FEATURE_AWARE_BLOCKED_COPY =
  'Forecast not available for feature-aware models — use the What-If Planner ' +
  '(Scenarios) to forecast through explicit assumptions.'

/** The promotion-is-audited note shown in the promote dialog. */
export const PROMOTE_AUDIT_NOTE =
  'Promotion is explicit and recorded — the approver and decision are saved as ' +
  'an audit record on this run. It is never automatic.'

export const SAFETY_STOCK_HEADER = 'Safety stock (heuristic)'
