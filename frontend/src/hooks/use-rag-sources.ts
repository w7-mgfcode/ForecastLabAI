import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type {
  SourceListResponse,
  IndexDocumentRequest,
  IndexDocumentResponse,
  RetrieveRequest,
  RetrieveResponse,
} from '@/types/api'

export function useRagSources() {
  return useQuery({
    queryKey: ['rag-sources'],
    queryFn: () => api<SourceListResponse>('/rag/sources'),
  })
}

export function useDeleteRagSource() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (sourceId: string) =>
      api<void>(`/rag/sources/${sourceId}`, { method: 'DELETE' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['rag-sources'] })
    },
  })
}

export function useIndexDocument() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: IndexDocumentRequest) =>
      api<IndexDocumentResponse>('/rag/index', {
        method: 'POST',
        body: data,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['rag-sources'] })
    },
  })
}

// Mutation: semantic search over the knowledge base (POST /rag/retrieve).
// Search results are ephemeral — no cache invalidation. A 502 (no embedding
// provider configured) surfaces as an ApiError the caller degrades gracefully.
export function useRetrieve() {
  return useMutation({
    mutationFn: (body: RetrieveRequest) =>
      api<RetrieveResponse>('/rag/retrieve', { method: 'POST', body }),
  })
}
