import type { ModelSelectionStatus } from '@/types/api'

/**
 * Terminal selection-run statuses (Slice B). Polling stops once a run reaches
 * one of these. Kept in a `.ts` module so the
 * `react-refresh/only-export-components` lint rule never trips.
 */
export const TERMINAL_SELECTION_STATES: ReadonlySet<ModelSelectionStatus> = new Set([
  'completed',
  'partial',
  'failed',
  'cancelled',
])

export function isTerminalSelectionStatus(status: ModelSelectionStatus): boolean {
  return TERMINAL_SELECTION_STATES.has(status)
}
