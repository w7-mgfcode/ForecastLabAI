import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { LifecycleCurveResponse } from '@/types/api'

interface UseLifecycleCurveParams {
  startDate?: string
  endDate?: string
  enabled?: boolean
}

/** GET /dimensions/products/{id}/lifecycle-curve — reference demand curve for a product. */
export function useLifecycleCurve(
  productId: number,
  { startDate, endDate, enabled = true }: UseLifecycleCurveParams = {}
) {
  return useQuery({
    queryKey: ['lifecycle-curve', productId, { startDate, endDate }],
    queryFn: () =>
      api<LifecycleCurveResponse>(`/dimensions/products/${productId}/lifecycle-curve`, {
        params: {
          start_date: startDate,
          end_date: endDate,
        },
      }),
    enabled: enabled && productId > 0,
  })
}
