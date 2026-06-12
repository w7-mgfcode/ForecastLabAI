import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
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

/**
 * Delete a saved workspace METADATA row; invalidates the workspaces list on
 * success. Server-side this removes only the `showcase_workspace` record —
 * the run's created objects (model runs, scenario plans, aliases, jobs,
 * artifacts) are soft references and stay untouched.
 */
export function useDeleteWorkspace() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (workspaceId: string) =>
      api<void>(`/demo/workspaces/${workspaceId}`, { method: 'DELETE' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['workspaces'] })
    },
  })
}
