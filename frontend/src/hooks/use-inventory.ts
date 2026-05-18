import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { InventoryStatusResponse } from '@/types/api'

interface UseInventoryParams {
  storeId?: number
  productId?: number
  enabled?: boolean
}

/** GET /analytics/inventory-status — latest snapshot per (store, product) grain. */
export function useInventoryStatus({
  storeId,
  productId,
  enabled = true,
}: UseInventoryParams) {
  return useQuery({
    queryKey: ['inventory-status', { storeId, productId }],
    queryFn: () =>
      api<InventoryStatusResponse>('/analytics/inventory-status', {
        params: {
          store_id: storeId,
          product_id: productId,
        },
      }),
    placeholderData: keepPreviousData,
    enabled,
  })
}
