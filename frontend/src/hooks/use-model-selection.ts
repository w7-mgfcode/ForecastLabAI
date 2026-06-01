import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { ModelCatalogResponse, PairAvailability } from '@/types/api'

/**
 * Model-selection query hooks (Champion Selector, Slice A).
 *
 * Read-only: the catalog and pair-availability GETs. The run mutation,
 * progress, and results hooks are owned by Slice B; train/predict by Slice C.
 */

/**
 * Fetch the backend-owned candidate-model capability catalog.
 *
 * The catalog is static, so it is cached aggressively (no refetch churn).
 */
export function useModelCatalog() {
  return useQuery({
    queryKey: ['model-selection', 'models'],
    queryFn: () => api<ModelCatalogResponse>('/model-selection/models'),
    staleTime: 1000 * 60 * 60, // 1h — the catalog rarely changes within a session
  })
}

interface UsePairAvailabilityParams {
  storeId: number | null
  productId: number | null
  forecastHorizon: number
  enabled?: boolean
}

/**
 * Assess data availability for a (store, product) pair at a given horizon.
 *
 * Gated like `useStore`: only fires once a real pair is chosen. `storeId` /
 * `productId` are nullable so the page can pass its raw selection state without
 * coercing un-selected values to a bogus `0`/`1`.
 */
export function usePairAvailability({
  storeId,
  productId,
  forecastHorizon,
  enabled = true,
}: UsePairAvailabilityParams) {
  return useQuery({
    queryKey: ['model-selection', 'availability', storeId, productId, forecastHorizon],
    queryFn: () =>
      api<PairAvailability>('/model-selection/availability', {
        params: {
          store_id: storeId,
          product_id: productId,
          forecast_horizon: forecastHorizon,
        },
      }),
    enabled: enabled && !!storeId && storeId > 0 && !!productId && productId > 0,
  })
}
