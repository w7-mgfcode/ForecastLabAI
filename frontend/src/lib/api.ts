import type { ProblemDetail } from '@/types/api'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8123'

interface RequestConfig {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
  params?: Record<string, string | number | boolean | undefined | null>
  signal?: AbortSignal
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public detail?: ProblemDetail
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function api<T>(endpoint: string, config: RequestConfig = {}): Promise<T> {
  const { method = 'GET', body, params, signal } = config

  const url = new URL(`${API_BASE_URL}${endpoint}`)
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        url.searchParams.set(key, String(value))
      }
    })
  }

  const response = await fetch(url.toString(), {
    method,
    headers: {
      'Content-Type': 'application/json',
    },
    body: body ? JSON.stringify(body) : undefined,
    signal,
  })

  // Handle 204 No Content
  if (response.status === 204) {
    return undefined as T
  }

  // Handle 202 Accepted (for async job creation)
  if (response.status === 202) {
    const data = await response.json()
    return data as T
  }

  const data = await response.json()

  if (!response.ok) {
    const detail = data as ProblemDetail
    throw new ApiError(
      detail.detail || response.statusText,
      response.status,
      detail
    )
  }

  return data as T
}

// Helper for consistent error messages
export function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.detail?.detail || error.message
  }
  if (error instanceof Error) {
    return error.message
  }
  return 'An unexpected error occurred'
}

// Currency formatting helper
export function formatCurrency(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return '-'
  const numValue = typeof value === 'string' ? parseFloat(value) : value
  if (isNaN(numValue)) return '-'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(numValue)
}

// Number formatting helper
export function formatNumber(value: number | null | undefined, decimals = 0): string {
  if (value === null || value === undefined) return '-'
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value)
}

// Percentage formatting helper
export function formatPercent(value: string | number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined) return '-'
  const numValue = typeof value === 'string' ? parseFloat(value) : value
  if (isNaN(numValue)) return '-'
  return `${numValue.toFixed(decimals)}%`
}
