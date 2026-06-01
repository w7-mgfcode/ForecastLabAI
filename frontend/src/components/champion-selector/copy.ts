/**
 * Shared, LOCKED copy for the Champion Selector workflow (Slices A/B/C).
 *
 * Kept in a `.ts` (not `.tsx`) module so the `react-refresh/only-export-components`
 * lint rule never trips on these non-component exports. Slices B and C import
 * the SAME constants so the bias wording / tie-break explanation never drift.
 */

/** LOCKED #7 — the canonical bias explanation reused everywhere bias is shown. */
export const BIAS_EXPLANATION =
  'Positive bias means the model under-forecasts (risk of stockouts); ' +
  'negative bias means it over-forecasts (risk of overstock).'

/** LOCKED #8 — the deterministic ranking tie-break chain. */
export const RANKING_TIE_BREAK =
  'Ranked by WAPE, then sMAPE, then |bias|, then MAE.'

/** Copy for the disabled Slice-A "Run comparison" CTA. */
export const RUN_COMPARISON_PENDING =
  'Model comparison runs in the next update.'
