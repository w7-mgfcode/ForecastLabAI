import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { WorkspaceDetail, WorkspaceListResponse } from '@/types/api'

/**
 * E4 (#393) — list saved showcase workspaces, newest first. Server-backed
 * source of truth for `preservation="keep"` runs (the localStorage
 * RunHistoryStrip stays ephemeral-only).
 */
export function useWorkspaces(limit = 20, enabled = true) {
  return useQuery({
    queryKey: ['workspaces', { limit }],
    queryFn: () => api<WorkspaceListResponse>('/demo/workspaces', { params: { limit } }),
    enabled,
  })
}

/** E4 (#393) — fetch one workspace, including its created-object soft references. */
export function useWorkspace(workspaceId: string, enabled = true) {
  return useQuery({
    queryKey: ['workspaces', workspaceId],
    queryFn: () => api<WorkspaceDetail>(`/demo/workspaces/${workspaceId}`),
    enabled: enabled && !!workspaceId,
  })
}
