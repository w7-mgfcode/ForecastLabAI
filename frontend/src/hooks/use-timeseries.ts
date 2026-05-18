import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { TimeGranularity, TimeSeriesResponse } from '@/types/api'

interface UseTimeseriesParams {
  startDate: string
  endDate: string
  granularity?: TimeGranularity
  storeId?: number
  productId?: number
  category?: string
  enabled?: boolean
}

/** GET /analytics/timeseries — period-bucketed sales for revenue-over-time charts. */
export function useTimeseries({
  startDate,
  endDate,
  granularity = 'day',
  storeId,
  productId,
  category,
  enabled = true,
}: UseTimeseriesParams) {
  return useQuery({
    queryKey: ['timeseries', { startDate, endDate, granularity, storeId, productId, category }],
    queryFn: () =>
      api<TimeSeriesResponse>('/analytics/timeseries', {
        params: {
          start_date: startDate,
          end_date: endDate,
          granularity,
          store_id: storeId,
          product_id: productId,
          category,
        },
      }),
    placeholderData: keepPreviousData,
    enabled: enabled && !!startDate && !!endDate,
  })
}
