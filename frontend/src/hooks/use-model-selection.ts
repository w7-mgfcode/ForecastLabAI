import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { isTerminalSelectionStatus } from '@/components/champion-selector/results/constants'
import type {
  ForecastDecisionParams,
  ModelCatalogResponse,
  ModelSelectionRunRequest,
  ModelSelectionRunResponse,
  PairAvailability,
  PredictWinnerResponse,
  PromoteRequest,
  PromoteResponse,
  SubmitRunResponse,
  TrainSelectedRequest,
  TrainWinnerResponse,
} from '@/types/api'

/**
 * Model-selection query hooks (Champion Selector).
 *
 * Slice A: catalog + availability GETs. Slice B: async submit / poll / cancel.
 * Slice C: train (winner / override) / predict (decision) / promote.
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

/**
 * Submit an async selection run (Slice B). `POST /model-selection/runs` returns
 * 202 immediately; we seed the poll cache so `useSelectionRun` starts warm.
 */
export function useSubmitSelectionRun() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (request: ModelSelectionRunRequest) =>
      api<SubmitRunResponse>('/model-selection/runs', {
        method: 'POST',
        body: request,
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(['model-selection', 'run', data.selection_id], data)
    },
  })
}

/**
 * Poll one selection run. Refetches every 2s while pending/running, then stops
 * once the run reaches a terminal status. Gated on a real selection id.
 */
export function useSelectionRun(selectionId: string | null, enabled = true) {
  return useQuery({
    queryKey: ['model-selection', 'run', selectionId],
    queryFn: () =>
      api<ModelSelectionRunResponse>(`/model-selection/${selectionId}`),
    enabled: enabled && !!selectionId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status && isTerminalSelectionStatus(status) ? false : 2000
    },
  })
}

/**
 * Cancel an in-flight selection run (Slice B). `DELETE /model-selection/{id}` —
 * 200 settled / 404 / 409 terminal / 504 drain timeout. Seeds + invalidates the
 * poll query on success.
 */
export function useCancelSelectionRun() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (selectionId: string) =>
      api<ModelSelectionRunResponse>(`/model-selection/${selectionId}`, {
        method: 'DELETE',
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(['model-selection', 'run', data.selection_id], data)
      void queryClient.invalidateQueries({
        queryKey: ['model-selection', 'run', data.selection_id],
      })
    },
  })
}

/**
 * Invalidate the polled run query so a terminal run re-fetches the new
 * `final_model_path` / `forecast` / promotion after a Slice C mutation.
 */
function invalidateRun(
  queryClient: ReturnType<typeof useQueryClient>,
  selectionId: string,
) {
  void queryClient.invalidateQueries({
    queryKey: ['model-selection', 'run', selectionId],
  })
}

/** Train the ranked winner (`POST /{id}/train-winner`, no body). */
export function useTrainWinner(selectionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () =>
      api<TrainWinnerResponse>(`/model-selection/${selectionId}/train-winner`, {
        method: 'POST',
      }),
    onSuccess: () => invalidateRun(queryClient, selectionId),
  })
}

/** Train a user-chosen candidate (`POST /{id}/train-selected`, override). */
export function useTrainSelected(selectionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: TrainSelectedRequest) =>
      api<TrainWinnerResponse>(`/model-selection/${selectionId}/train-selected`, {
        method: 'POST',
        body,
      }),
    onSuccess: () => invalidateRun(queryClient, selectionId),
  })
}

/** Forecast with the trained model + decision (`POST /{id}/predict`). */
export function usePredictWinner(selectionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ForecastDecisionParams) =>
      api<PredictWinnerResponse>(`/model-selection/${selectionId}/predict`, {
        method: 'POST',
        body,
      }),
    onSuccess: () => invalidateRun(queryClient, selectionId),
  })
}

/** Promote the trained champion to a registry alias (`POST /{id}/promote`). */
export function usePromoteChampion(selectionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: PromoteRequest) =>
      api<PromoteResponse>(`/model-selection/${selectionId}/promote`, {
        method: 'POST',
        body,
      }),
    onSuccess: () => invalidateRun(queryClient, selectionId),
  })
}
