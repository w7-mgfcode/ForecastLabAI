// Pure, React-free helpers for the ForecastOps Control Center page. Kept
// separate from the page component so they are cheap to unit-test (see
// ops-utils.test.ts) — mirrors the knowledge-utils.ts / status-utils.ts precedent.
import { ROUTES } from '@/lib/constants'
import type { AttentionItem, RetrainingCandidate, SystemHealth } from '@/types/api'

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
