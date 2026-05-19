import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type {
  CreateScenarioRequest,
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

/** List saved scenario plans, newest first. */
export function useScenarios(enabled = true) {
  return useQuery({
    queryKey: ['scenarios'],
    queryFn: () => api<ScenarioListResponse>('/scenarios'),
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
