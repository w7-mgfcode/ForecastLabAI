import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '@/lib/api'
import type {
  WorkspaceDetail,
  WorkspaceExportResult,
  WorkspaceHealth,
  WorkspaceListParams,
  WorkspaceListResponse,
  WorkspaceUpdate,
} from '@/types/api'

/**
 * E4 (#393) — list saved showcase workspaces. Server-backed source of truth
 * for `preservation="keep"` runs (the localStorage RunHistoryStrip stays
 * ephemeral-only). E2 (#408) — params-aware: q name search, single-tag
 * filter, include_archived (server default hides archived), allow-listed
 * sort_by/sort_order. Pinned rows always order first server-side.
 */
export function useWorkspaces(params: WorkspaceListParams = {}, enabled = true) {
  return useQuery({
    queryKey: ['workspaces', params],
    queryFn: () =>
      api<WorkspaceListResponse>('/demo/workspaces', {
        params: {
          limit: params.limit ?? 20,
          offset: params.offset,
          q: params.q,
          tags: params.tags,
          include_archived: params.include_archived,
          sort_by: params.sort_by,
          sort_order: params.sort_order,
        },
      }),
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

/**
 * E2 (#408) — partial lifecycle update (rename / notes / tags / pin /
 * archive) through the E1 PATCH endpoint. Only provided fields change.
 * Invalidates the blanket ['workspaces'] key so list + detail + lineage
 * queries all refetch.
 */
export function usePatchWorkspace() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ workspaceId, update }: { workspaceId: string; update: WorkspaceUpdate }) =>
      api<WorkspaceDetail>(`/demo/workspaces/${workspaceId}`, {
        method: 'PATCH',
        body: update,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['workspaces'] })
    },
  })
}

/**
 * E2 (#408) — soft-reference link health for the LOADED workspace only
 * (never probed per list row — the backend fans out one in-process probe
 * per reference). staleTime keeps reloads from hammering the probe fan-out.
 */
export function useWorkspaceHealth(workspaceId: string, enabled = true) {
  return useQuery({
    queryKey: ['workspaces', workspaceId, 'health'],
    queryFn: () => api<WorkspaceHealth>(`/demo/workspaces/${workspaceId}/health`),
    enabled: enabled && !!workspaceId,
    staleTime: 30_000,
  })
}

/**
 * E6 (#412) — export a saved workspace to a checksum-validated bundle on disk
 * (artifacts/showcase/<id>/). Export is stateless and re-runnable: it writes no
 * server-side row, so it does NOT invalidate the workspaces list.
 */
export function useExportWorkspace() {
  return useMutation({
    mutationFn: (workspaceId: string) =>
      api<WorkspaceExportResult>(`/demo/workspaces/${workspaceId}/export`, { method: 'POST' }),
  })
}

/** One ancestor entry in a workspace's replay lineage chain (newest first). */
export interface LineageEntry {
  workspace_id: string
  name: string | null
  /** True when the ancestor row was deleted — dangling pointers are designed. */
  deleted: boolean
  detail: WorkspaceDetail | null
}

export interface WorkspaceLineage {
  entries: LineageEntry[]
  /** True when the chain continues past the depth cap. */
  truncated: boolean
}

// A replay-of-a-replay chain deeper than this is pathological; the strip
// renders a trailing ellipsis instead of walking forever.
const LINEAGE_DEPTH_CAP = 5

/**
 * E2 (#408) — walk the replayed_from_workspace_id chain (newest → original)
 * as ONE query of serial fetches. A 404 ancestor terminates the walk with a
 * deleted sentinel — dangling lineage is expected, never an error.
 */
export function useWorkspaceLineage(workspaceId: string | null) {
  return useQuery({
    queryKey: ['workspaces', workspaceId, 'lineage'],
    enabled: !!workspaceId,
    queryFn: async (): Promise<WorkspaceLineage> => {
      const entries: LineageEntry[] = []
      let current: string | null = workspaceId
      for (let depth = 0; depth < LINEAGE_DEPTH_CAP && current; depth += 1) {
        try {
          const detail = await api<WorkspaceDetail>(`/demo/workspaces/${current}`)
          entries.push({
            workspace_id: current,
            name: detail.name,
            deleted: false,
            detail,
          })
          current = detail.replayed_from_workspace_id
        } catch (error) {
          if (error instanceof ApiError && error.status === 404) {
            entries.push({ workspace_id: current, name: null, deleted: true, detail: null })
            current = null
          } else {
            throw error
          }
        }
      }
      return { entries, truncated: current !== null }
    },
  })
}
