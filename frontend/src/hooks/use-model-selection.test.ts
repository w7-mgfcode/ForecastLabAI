/**
 * Unit tests for the model-selection query hooks (Champion Selector, Slice A).
 *
 * Stubs `fetch` to assert the catalog + availability GET URLs and the
 * availability `enabled` gating. No real backend is exercised.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createElement, type ReactNode } from 'react'

import { useModelCatalog, usePairAvailability } from './use-model-selection'
import type { ModelCatalogResponse, PairAvailability } from '@/types/api'

function makeWrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client }, children)
  }
}

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

const CATALOG: ModelCatalogResponse = {
  models: [
    {
      model_type: 'naive',
      label: 'Naive',
      family: 'baseline',
      feature_aware: false,
      requires_extra: false,
      default_params: {},
      supports_auto_predict: true,
      description: 'Repeats the last observed value.',
    },
  ],
  default_candidate_model_types: ['naive', 'seasonal_naive', 'moving_average'],
}

const AVAILABILITY: PairAvailability = {
  store_id: 7,
  product_id: 12,
  first_sales_date: '2026-01-01',
  last_sales_date: '2026-05-31',
  observed_days: 150,
  expected_calendar_days: 151,
  coverage_ratio: 0.99,
  missing_days: 1,
  zero_sale_days: 4,
  promotion_days: 3,
  average_daily_demand: 9.2,
  status: 'ready',
  recommended_split_config: {
    strategy: 'expanding',
    n_splits: 5,
    min_train_size: 30,
    gap: 0,
    horizon: 14,
  },
  warnings: [],
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useModelCatalog', () => {
  it('GETs /model-selection/models and returns the parsed catalog', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(CATALOG), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useModelCatalog(), {
      wrapper: makeWrapper(makeClient()),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0]![0]).toContain('/model-selection/models')
    expect(result.current.data?.models[0]?.model_type).toBe('naive')
  })
})

describe('usePairAvailability', () => {
  it('GETs /model-selection/availability with the three query params', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(AVAILABILITY), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(
      () => usePairAvailability({ storeId: 7, productId: 12, forecastHorizon: 14 }),
      { wrapper: makeWrapper(makeClient()) },
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const url = String(fetchMock.mock.calls[0]![0])
    expect(url).toContain('/model-selection/availability')
    expect(url).toContain('store_id=7')
    expect(url).toContain('product_id=12')
    expect(url).toContain('forecast_horizon=14')
    expect(result.current.data?.status).toBe('ready')
  })

  it('does NOT fetch while the pair is incomplete (enabled gating)', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    renderHook(
      () => usePairAvailability({ storeId: null, productId: 12, forecastHorizon: 14 }),
      { wrapper: makeWrapper(makeClient()) },
    )

    // Give TanStack a tick; the disabled query must never call fetch.
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
