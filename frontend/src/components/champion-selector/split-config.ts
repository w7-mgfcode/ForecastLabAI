import type { SplitConfig } from '@/types/api'

/**
 * Inline-validate a `SplitConfig` against the backend SplitConfig bounds
 * (`app/features/backtesting/schemas.py`). Kept in a `.ts` module (not the
 * form `.tsx`) so the `react-refresh/only-export-components` lint rule stays
 * happy. Returns a list of human-facing error strings (empty = valid).
 */
export function splitConfigErrors(config: SplitConfig): string[] {
  const errors: string[] = []
  if (config.n_splits < 2 || config.n_splits > 20) {
    errors.push('Splits must be between 2 and 20.')
  }
  if (config.min_train_size < 7) {
    errors.push('Minimum train size must be at least 7 days.')
  }
  if (config.gap < 0 || config.gap > 30) {
    errors.push('Gap must be between 0 and 30 days.')
  }
  if (config.gap >= config.horizon) {
    errors.push('Gap must be smaller than the horizon.')
  }
  return errors
}
