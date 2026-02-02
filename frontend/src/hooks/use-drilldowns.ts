import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { DrilldownResponse, DrilldownDimension } from '@/types/api'

interface UseDrilldownsParams {
  dimension: DrilldownDimension
  startDate: string
  endDate: string
  storeId?: number
  productId?: number
  maxItems?: number
  enabled?: boolean
}

export function useDrilldowns({
  dimension,
  startDate,
  endDate,
  storeId,
  productId,
  maxItems = 10,
  enabled = true,
}: UseDrilldownsParams) {
  return useQuery({
    queryKey: ['drilldowns', { dimension, startDate, endDate, storeId, productId, maxItems }],
    queryFn: () =>
      api<DrilldownResponse>('/analytics/drilldowns', {
        params: {
          dimension,
          start_date: startDate,
          end_date: endDate,
          store_id: storeId,
          product_id: productId,
          max_items: maxItems,
        },
      }),
    placeholderData: keepPreviousData,
    enabled: enabled && !!startDate && !!endDate,
  })
}
