import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type {
  SeederStatus,
  ScenarioInfo,
  GenerateParams,
  GenerateResult,
  AppendParams,
  DeleteParams,
  DeleteResult,
  VerifyResult,
} from '@/types/api'

// Query: Get database status (row counts, date range)
export function useSeederStatus() {
  return useQuery({
    queryKey: ['seeder', 'status'],
    queryFn: () => api<SeederStatus>('/seeder/status'),
    // Refresh every 30 seconds to catch external changes
    refetchInterval: 30000,
  })
}

// Query: Get available scenarios (cached indefinitely - they don't change)
export function useSeederScenarios() {
  return useQuery({
    queryKey: ['seeder', 'scenarios'],
    queryFn: () => api<ScenarioInfo[]>('/seeder/scenarios'),
    staleTime: Infinity,
  })
}

// Mutation: Generate new dataset
export function useGenerateData() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (params: GenerateParams) =>
      api<GenerateResult>('/seeder/generate', { method: 'POST', body: params }),
    onSuccess: () => {
      // Invalidate status to refresh counts
      void queryClient.invalidateQueries({ queryKey: ['seeder', 'status'] })
      // Also invalidate analytics as data changed
      void queryClient.invalidateQueries({ queryKey: ['analytics'] })
      void queryClient.invalidateQueries({ queryKey: ['kpis'] })
    },
  })
}

// Mutation: Append data to existing dataset
export function useAppendData() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (params: AppendParams) =>
      api<GenerateResult>('/seeder/append', { method: 'POST', body: params }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['seeder', 'status'] })
      void queryClient.invalidateQueries({ queryKey: ['analytics'] })
      void queryClient.invalidateQueries({ queryKey: ['kpis'] })
    },
  })
}

// Mutation: Delete data
export function useDeleteData() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (params: DeleteParams) =>
      api<DeleteResult>('/seeder/data', { method: 'DELETE', body: params }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['seeder', 'status'] })
      void queryClient.invalidateQueries({ queryKey: ['analytics'] })
      void queryClient.invalidateQueries({ queryKey: ['kpis'] })
    },
  })
}

// Mutation: Verify data integrity
export function useVerifyData() {
  return useMutation({
    mutationFn: () => api<VerifyResult>('/seeder/verify', { method: 'POST' }),
  })
}
