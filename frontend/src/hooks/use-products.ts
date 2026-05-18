import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { ProductListResponse, Product } from '@/types/api'

interface UseProductsParams {
  page: number
  pageSize: number
  category?: string
  brand?: string
  search?: string
  sortBy?: string
  sortOrder?: 'asc' | 'desc'
  enabled?: boolean
}

export function useProducts({
  page,
  pageSize,
  category,
  brand,
  search,
  sortBy,
  sortOrder,
  enabled = true,
}: UseProductsParams) {
  return useQuery({
    queryKey: ['products', { page, pageSize, category, brand, search, sortBy, sortOrder }],
    queryFn: () =>
      api<ProductListResponse>('/dimensions/products', {
        params: {
          page,
          page_size: pageSize,
          category,
          brand,
          search: search && search.length >= 2 ? search : undefined,
          sort_by: sortBy,
          sort_order: sortOrder,
        },
      }),
    placeholderData: keepPreviousData,
    enabled,
  })
}

export function useProduct(productId: number, enabled = true) {
  return useQuery({
    queryKey: ['products', productId],
    queryFn: () => api<Product>(`/dimensions/products/${productId}`),
    enabled: enabled && productId > 0,
  })
}
