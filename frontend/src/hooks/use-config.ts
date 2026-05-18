import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type {
  AIModelConfig,
  AIModelConfigUpdate,
  OllamaModel,
  ProviderHealth,
} from '@/types/api'

// Query: effective AI-model configuration (agent LLM + RAG embeddings).
export function useAIConfig() {
  return useQuery({
    queryKey: ['config', 'ai'],
    queryFn: () => api<AIModelConfig>('/config/ai'),
  })
}

// Query: per-provider connectivity (Ollama probed live, cloud keys by presence).
export function useProviderHealth() {
  return useQuery({
    queryKey: ['config', 'health'],
    queryFn: () => api<ProviderHealth[]>('/config/providers/health'),
  })
}

// Query: models pulled on the Ollama host. Opt-in via `enabled` so it only
// runs when the operator actually needs the picker (e.g. provider === ollama).
export function useOllamaModels(enabled: boolean) {
  return useQuery({
    queryKey: ['config', 'ollama-models'],
    queryFn: () => api<OllamaModel[]>('/config/ollama/models'),
    enabled,
    retry: false,
  })
}

// Mutation: persist + apply an AI-model configuration change (no restart).
export function useUpdateAIConfig() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: AIModelConfigUpdate) =>
      api<AIModelConfig>('/config/ai', { method: 'PATCH', body }),
    onSuccess: () => {
      // Refresh every config-derived view (effective config + provider health).
      void queryClient.invalidateQueries({ queryKey: ['config'] })
    },
  })
}
