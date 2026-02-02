import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { KPIResponse } from '@/types/api'

interface UseKPIsParams {
  startDate: string
  endDate: string
  storeId?: number
  productId?: number
  category?: string
  enabled?: boolean
}

export function useKPIs({
  startDate,
  endDate,
  storeId,
  productId,
  category,
  enabled = true,
}: UseKPIsParams) {
  return useQuery({
    queryKey: ['kpis', { startDate, endDate, storeId, productId, category }],
    queryFn: () =>
      api<KPIResponse>('/analytics/kpis', {
        params: {
          start_date: startDate,
          end_date: endDate,
          store_id: storeId,
          product_id: productId,
          category,
        },
      }),
    enabled: enabled && !!startDate && !!endDate,
  })
}
