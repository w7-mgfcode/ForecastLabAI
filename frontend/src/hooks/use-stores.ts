import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { StoreListResponse, Store } from '@/types/api'

interface UseStoresParams {
  page: number
  pageSize: number
  region?: string
  storeType?: string
  search?: string
  sortBy?: string
  sortOrder?: 'asc' | 'desc'
  enabled?: boolean
}

export function useStores({
  page,
  pageSize,
  region,
  storeType,
  search,
  sortBy,
  sortOrder,
  enabled = true,
}: UseStoresParams) {
  return useQuery({
    queryKey: ['stores', { page, pageSize, region, storeType, search, sortBy, sortOrder }],
    queryFn: () =>
      api<StoreListResponse>('/dimensions/stores', {
        params: {
          page,
          page_size: pageSize,
          region,
          store_type: storeType,
          search: search && search.length >= 2 ? search : undefined,
          sort_by: sortBy,
          sort_order: sortOrder,
        },
      }),
    placeholderData: keepPreviousData,
    enabled,
  })
}

export function useStore(storeId: number, enabled = true) {
  return useQuery({
    queryKey: ['stores', storeId],
    queryFn: () => api<Store>(`/dimensions/stores/${storeId}`),
    enabled: enabled && storeId > 0,
  })
}
