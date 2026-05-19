// Pure, React-free helpers for the ForecastOps Control Center page. Kept
// separate from the page component so they are cheap to unit-test (see
// ops-utils.test.ts) — mirrors the knowledge-utils.ts / status-utils.ts precedent.
import { ROUTES } from '@/lib/constants'
import type { AttentionItem, DriftDirection, RetrainingCandidate, SystemHealth } from '@/types/api'

/**
 * System-health badge variant: 'success' only when the API and database are
 * both up, 'error' otherwise.
 */
export function summaryHealthVariant(system: SystemHealth): 'success' | 'error' {
  return system.api_ok && system.database_connected ? 'success' : 'error'
}

/**
 * Deep-link an attention item to its Explorer detail page. A failed job links
 * to the job detail page; a failed run and a stale alias both carry a run_id
 * and link to the run detail page.
 */
export function attentionItemLink(item: AttentionItem): string {
  if (item.item_type === 'failed_job') {
    return `${ROUTES.EXPLORER.JOBS}/${item.entity_id}`
  }
  return `${ROUTES.EXPLORER.RUNS}/${item.entity_id}`
}

/**
 * Badge variant for an attention row — a stale alias is a 'warning', a failed
 * job or run is an 'error'.
 */
export function attentionBadgeVariant(
  itemType: AttentionItem['item_type'],
): 'error' | 'warning' {
  return itemType === 'stale_alias' ? 'warning' : 'error'
}

/**
 * Human-readable staleness: "today" at zero or negative days, "{n}d" otherwise.
 */
export function formatStaleness(days: number): string {
  return days <= 0 ? 'today' : `${days}d`
}

/**
 * Return a copy of the candidates sorted by priority score, most urgent first.
 * The backend already sorts, but sorting again keeps the page correct if the
 * order ever changes upstream.
 */
export function sortRetrainingCandidates(rows: RetrainingCandidate[]): RetrainingCandidate[] {
  return [...rows].sort((a, b) => b.priority_score - a.priority_score)
}

/**
 * Badge variant for a drift verdict — 'degrading' is an error, 'improving' a
 * success, 'stable' an info, and 'unknown' a neutral default.
 */
export function driftBadgeVariant(
  direction: DriftDirection,
): 'success' | 'error' | 'info' | 'default' {
  switch (direction) {
    case 'degrading':
      return 'error'
    case 'improving':
      return 'success'
    case 'stable':
      return 'info'
    default:
      return 'default'
  }
}

/**
 * Signed, one-decimal WAPE delta for display ("+14.0" / "-9.3"); '—' when the
 * grain has fewer than two numeric WAPEs (delta is null).
 */
export function formatWapeDelta(delta: number | null): string {
  if (delta === null) return '—'
  const sign = delta > 0 ? '+' : ''
  return `${sign}${delta.toFixed(1)}`
}
