import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { SourceListResponse, IndexDocumentRequest, IndexDocumentResponse } from '@/types/api'

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
