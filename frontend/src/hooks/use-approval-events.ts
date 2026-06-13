import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { ApprovalEventsResponse } from '@/types/api'

/**
 * E5 (#411) — recent HITL approval events flattened across saved showcase
 * workspaces, newest-first. Deliberately NOT polled: the table only changes
 * when a showcase run finishes capturing a decision, so refetch-on-mount is
 * sufficient (mirrors useRetrainingCandidates). queryKey carries `limit` so
 * distinct caps cache independently.
 */
export function useApprovalEvents(limit = 50, enabled = true) {
  return useQuery({
    queryKey: ['demo', 'approval-events', limit],
    queryFn: () =>
      api<ApprovalEventsResponse>('/demo/approval-events', { params: { limit } }),
    enabled,
  })
}
