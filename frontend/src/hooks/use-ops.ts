import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { OpsSummaryResponse, RetrainingCandidatesResponse } from '@/types/api'

/**
 * Operational summary for the Control Center. Polled every 15s — job/run state
 * changes quickly. The global query client already disables refetch-on-focus,
 * so this will not double-fire when the tab regains focus.
 */
export function useOpsSummary(enabled = true) {
  return useQuery({
    queryKey: ['ops', 'summary'],
    queryFn: () => api<OpsSummaryResponse>('/ops/summary'),
    refetchInterval: 15000,
    enabled,
  })
}

/**
 * Ranked retraining-candidate queue. Deliberately NOT polled — the queue only
 * changes when a new run lands, so refetch-on-mount is sufficient.
 */
export function useRetrainingCandidates(limit = 20, enabled = true) {
  return useQuery({
    queryKey: ['ops', 'retraining', limit],
    queryFn: () =>
      api<RetrainingCandidatesResponse>('/ops/retraining-candidates', { params: { limit } }),
    enabled,
  })
}
