import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import type {
  BatchItemListResponse,
  BatchSubmitRequest,
  BatchSubmitResponse,
} from '@/types/api'

// Submit a new batch. The backend runs the items synchronously and returns
// the settled parent; mutation success invalidates batch + items caches so
// downstream queries refetch.
export function useSubmitBatch() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: BatchSubmitRequest) =>
      api<BatchSubmitResponse>('/batch/forecasting', {
        method: 'POST',
        body: data,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['batch'] })
    },
  })
}

// Get a batch's parent record. Polls every 2s while the run is in-flight;
// stops polling once the parent settles to a terminal state.
export function useBatch(batchId: string | null, enabled = true) {
  return useQuery({
    queryKey: ['batch', batchId],
    queryFn: () => api<BatchSubmitResponse>(`/batch/${batchId}`),
    enabled: enabled && !!batchId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'pending' || status === 'running' ? 2000 : false
    },
  })
}

interface UseBatchItemsParams {
  batchId: string | null
  page?: number
  pageSize?: number
  sortBy?: string
  sortOrder?: 'asc' | 'desc'
  enabled?: boolean
}

export function useBatchItems({
  batchId,
  page = 1,
  pageSize = 50,
  sortBy,
  sortOrder = 'asc',
  enabled = true,
}: UseBatchItemsParams) {
  return useQuery({
    queryKey: ['batch', batchId, 'items', { page, pageSize, sortBy, sortOrder }],
    queryFn: () =>
      api<BatchItemListResponse>(`/batch/${batchId}/items`, {
        params: {
          page,
          page_size: pageSize,
          sort_by: sortBy,
          sort_order: sortOrder,
        },
      }),
    enabled: enabled && !!batchId,
  })
}
