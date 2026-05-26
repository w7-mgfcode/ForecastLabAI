import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type {
  RunListResponse,
  ModelRun,
  Alias,
  RunCompareResponse,
  RunStatus,
  ArtifactVerifyResponse,
  FeatureFrameVersion,
} from '@/types/api'

interface UseRunsParams {
  page: number
  pageSize: number
  modelType?: string
  status?: RunStatus
  storeId?: number
  productId?: number
  sortBy?: string
  sortOrder?: 'asc' | 'desc'
  /**
   * PRP-37 — accepted by the hook so callers can keep one filter object;
   * NOT forwarded to the registry list endpoint today (no backend filter
   * exists). Used purely to scope the query key for client-side caches.
   */
  featureFrameVersion?: FeatureFrameVersion
  enabled?: boolean
}

export function useRuns({
  page,
  pageSize,
  modelType,
  status,
  storeId,
  productId,
  sortBy,
  sortOrder,
  featureFrameVersion,
  enabled = true,
}: UseRunsParams) {
  return useQuery({
    queryKey: [
      'runs',
      {
        page,
        pageSize,
        modelType,
        status,
        storeId,
        productId,
        sortBy,
        sortOrder,
        featureFrameVersion,
      },
    ],
    queryFn: () =>
      api<RunListResponse>('/registry/runs', {
        params: {
          page,
          page_size: pageSize,
          model_type: modelType,
          status,
          store_id: storeId,
          product_id: productId,
          sort_by: sortBy,
          sort_order: sortOrder,
          // NOTE: featureFrameVersion is intentionally NOT forwarded — see
          // PRP-37 Task 23 + contract probe report (no backend filter).
        },
      }),
    placeholderData: keepPreviousData,
    enabled,
  })
}

export function useRun(runId: string, enabled = true) {
  return useQuery({
    queryKey: ['runs', runId],
    queryFn: () => api<ModelRun>(`/registry/runs/${runId}`),
    enabled: enabled && !!runId,
  })
}

export function useCompareRuns(runIdA: string, runIdB: string, enabled = false) {
  return useQuery({
    queryKey: ['runs', 'compare', runIdA, runIdB],
    queryFn: () => api<RunCompareResponse>(`/registry/compare/${runIdA}/${runIdB}`),
    enabled: enabled && !!runIdA && !!runIdB,
  })
}

/**
 * Button-gated artifact integrity check. Pass `enabled` from component state
 * (false until the user clicks "Verify"), then call `refetch()` to re-run.
 * The endpoint returns HTTP 200 with `verified:false` on a checksum mismatch
 * and only errors (404/400) for a missing run/artifact.
 */
export function useVerifyArtifact(runId: string, enabled = false) {
  return useQuery({
    queryKey: ['runs', runId, 'verify'],
    queryFn: () => api<ArtifactVerifyResponse>(`/registry/runs/${runId}/verify`),
    enabled: enabled && !!runId,
    retry: false,
  })
}

export function useUpdateRun() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ runId, data }: { runId: string; data: Partial<ModelRun> }) =>
      api<ModelRun>(`/registry/runs/${runId}`, { method: 'PATCH', body: data }),
    onSuccess: (_, { runId }) => {
      void queryClient.invalidateQueries({ queryKey: ['runs'] })
      void queryClient.invalidateQueries({ queryKey: ['runs', runId] })
    },
  })
}

export function useAliases() {
  return useQuery({
    queryKey: ['aliases'],
    queryFn: () => api<Alias[]>('/registry/aliases'),
  })
}

export function useAlias(aliasName: string, enabled = true) {
  return useQuery({
    queryKey: ['aliases', aliasName],
    queryFn: () => api<Alias>(`/registry/aliases/${aliasName}`),
    enabled: enabled && !!aliasName,
  })
}

export function useCreateAlias() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: { alias_name: string; run_id: string; description?: string }) =>
      api<Alias>('/registry/aliases', { method: 'POST', body: data }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['aliases'] })
    },
  })
}

export function useDeleteAlias() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (aliasName: string) =>
      api<void>(`/registry/aliases/${aliasName}`, { method: 'DELETE' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['aliases'] })
    },
  })
}
