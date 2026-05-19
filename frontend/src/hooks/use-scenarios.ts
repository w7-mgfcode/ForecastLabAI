import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type {
  CompareScenariosRequest,
  CreateScenarioRequest,
  MultiScenarioComparison,
  ScenarioComparison,
  ScenarioListResponse,
  ScenarioPlanResponse,
  SimulateScenarioRequest,
} from '@/types/api'

/**
 * Run a stateless what-if simulation. A mutation, not a query — each run is an
 * explicit user action and the result is held in component state.
 */
export function useSimulateScenario() {
  return useMutation({
    mutationFn: (data: SimulateScenarioRequest) =>
      api<ScenarioComparison>('/scenarios/simulate', { method: 'POST', body: data }),
  })
}

/**
 * List saved scenario plans, newest first. Pass one or more `tags` to filter
 * to plans carrying every listed tag.
 */
export function useScenarios(tags: string[] = [], enabled = true) {
  const query =
    tags.length > 0
      ? `?${tags.map((tag) => `tags=${encodeURIComponent(tag)}`).join('&')}`
      : ''
  return useQuery({
    queryKey: ['scenarios', { tags }],
    queryFn: () => api<ScenarioListResponse>(`/scenarios${query}`),
    enabled,
  })
}

/** Fetch one saved plan, including its embedded comparison snapshot. */
export function useScenario(scenarioId: string, enabled = true) {
  return useQuery({
    queryKey: ['scenarios', scenarioId],
    queryFn: () => api<ScenarioPlanResponse>(`/scenarios/${scenarioId}`),
    enabled: enabled && !!scenarioId,
  })
}

/** Persist a scenario plan; invalidates the saved-plans list on success. */
export function useCreateScenario() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateScenarioRequest) =>
      api<ScenarioPlanResponse>('/scenarios', { method: 'POST', body: data }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['scenarios'] })
    },
  })
}

/** Delete a saved scenario plan; invalidates the saved-plans list on success. */
export function useDeleteScenario() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (scenarioId: string) =>
      api<void>(`/scenarios/${scenarioId}`, { method: 'DELETE' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['scenarios'] })
    },
  })
}

/**
 * Compare 2-5 saved scenario plans. A mutation, not a query — the comparison
 * is an explicit user action and the result is held in component state.
 */
export function useCompareScenarios() {
  return useMutation({
    mutationFn: (data: CompareScenariosRequest) =>
      api<MultiScenarioComparison>('/scenarios/compare', { method: 'POST', body: data }),
  })
}
