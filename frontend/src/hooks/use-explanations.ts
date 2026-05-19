import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { ForecastExplanation } from '@/types/api'

/**
 * Explain a registry model run. Disabled until `runId` is set. `retry: false`
 * because a 404 (no run) or 400 (non-baseline run) is a final answer, not a
 * transient failure.
 */
export function useRunExplanation(runId: string, enabled = true) {
  return useQuery({
    queryKey: ['explanations', 'run', runId],
    queryFn: () => api<ForecastExplanation>(`/explain/runs/${runId}`),
    enabled: enabled && !!runId,
    retry: false,
  })
}

/**
 * Explain a completed predict job. Disabled until `jobId` is set; `retry: false`
 * for the same reason as {@link useRunExplanation}.
 */
export function useJobExplanation(jobId: string, enabled = true) {
  return useQuery({
    queryKey: ['explanations', 'job', jobId],
    queryFn: () => api<ForecastExplanation>(`/explain/jobs/${jobId}`),
    enabled: enabled && !!jobId,
    retry: false,
  })
}

/** Request body for POST /explain/forecast. */
export interface ExplainForecastBody {
  store_id: number
  product_id: number
  model_type: 'naive' | 'seasonal_naive' | 'moving_average'
  as_of_date: string // ISO date
  season_length?: number
  window_size?: number
}

/** Run an ad-hoc forecast explanation. */
export function useExplainForecast() {
  return useMutation({
    mutationFn: (body: ExplainForecastBody) =>
      api<ForecastExplanation>('/explain/forecast', { method: 'POST', body }),
  })
}
