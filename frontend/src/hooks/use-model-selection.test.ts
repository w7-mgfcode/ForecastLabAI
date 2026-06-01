/**
 * Unit tests for the model-selection query hooks (Champion Selector, Slice A).
 *
 * Stubs `fetch` to assert the catalog + availability GET URLs and the
 * availability `enabled` gating. No real backend is exercised.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createElement, type ReactNode } from 'react'

import {
  useCancelSelectionRun,
  useModelCatalog,
  usePairAvailability,
  usePredictWinner,
  usePromoteChampion,
  useSelectionRun,
  useSubmitSelectionRun,
  useTrainSelected,
  useTrainWinner,
} from './use-model-selection'
import type {
  ModelCatalogResponse,
  ModelSelectionRunRequest,
  PairAvailability,
  SubmitRunResponse,
} from '@/types/api'

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

// --------------------------------------------------------------------- Slice B

const SUBMIT_RESPONSE: SubmitRunResponse = {
  selection_id: 'sel_b',
  store_id: 7,
  product_id: 12,
  status: 'running',
  selection_window: { start_date: '2026-01-01', end_date: '2026-05-31' },
  forecast_horizon: 14,
  ranking_metric: 'wape',
  availability: null,
  ranking: [],
  winner: null,
  recommendation_confidence: null,
  confidence_reasons: [],
  chart_data: null,
  final_model: null,
  forecast: null,
  business_summary: null,
  error_message: null,
  created_at: '2026-06-01T12:00:00Z',
  started_at: '2026-06-01T12:00:00Z',
  completed_at: null,
  progress: { total: 1, pending: 1, running: 0, completed: 0, failed: 0, cancelled: 0 },
  candidate_progress: [
    {
      candidate_id: 'c0',
      ordinal: 0,
      model_type: 'naive',
      status: 'pending',
      error: null,
      started_at: null,
      completed_at: null,
      duration_ms: null,
    },
  ],
  monitor_url: '/model-selection/sel_b',
  cancel_url: '/model-selection/sel_b',
}

const RUN_REQUEST: ModelSelectionRunRequest = {
  store_id: 7,
  product_id: 12,
  selection_window: { start_date: '2026-01-01', end_date: '2026-05-31' },
  forecast_horizon: 14,
  ranking_metric: 'wape',
  split_config: {
    strategy: 'expanding',
    n_splits: 5,
    min_train_size: 30,
    gap: 0,
    horizon: 14,
  },
  candidate_models: [{ model_type: 'naive', params: {} }],
  feature_frame_version: 1,
  feature_groups: null,
  auto_train_winner: false,
  auto_predict: false,
}

describe('useSubmitSelectionRun', () => {
  it('POSTs to /model-selection/runs and seeds the poll cache', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(SUBMIT_RESPONSE), {
        status: 202,
        headers: { 'content-type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const client = makeClient()
    const { result } = renderHook(() => useSubmitSelectionRun(), {
      wrapper: makeWrapper(client),
    })
    await act(async () => {
      result.current.mutate(RUN_REQUEST)
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const call = fetchMock.mock.calls[0]!
    expect(String(call[0])).toContain('/model-selection/runs')
    expect((call[1] as RequestInit).method).toBe('POST')
    // The poll cache is seeded so useSelectionRun starts warm.
    expect(
      client.getQueryData(['model-selection', 'run', 'sel_b']),
    ).toEqual(SUBMIT_RESPONSE)
  })
})

describe('useSelectionRun', () => {
  it('GETs /model-selection/{id} when given a selection id', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ...SUBMIT_RESPONSE, status: 'completed' }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useSelectionRun('sel_b'), {
      wrapper: makeWrapper(makeClient()),
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(String(fetchMock.mock.calls[0]![0])).toContain('/model-selection/sel_b')
    expect(result.current.data?.status).toBe('completed')
  })

  it('does NOT fetch without a selection id (enabled gating)', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    renderHook(() => useSelectionRun(null), { wrapper: makeWrapper(makeClient()) })
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('useCancelSelectionRun', () => {
  it('DELETEs /model-selection/{id}', async () => {
    const cancelled = { ...SUBMIT_RESPONSE, status: 'cancelled' as const }
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(cancelled), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useCancelSelectionRun(), {
      wrapper: makeWrapper(makeClient()),
    })
    await act(async () => {
      result.current.mutate('sel_b')
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const call = fetchMock.mock.calls[0]!
    expect(String(call[0])).toContain('/model-selection/sel_b')
    expect((call[1] as RequestInit).method).toBe('DELETE')
  })
})

// --------------------------------------------------------------- Slice C hooks

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

describe('useTrainWinner', () => {
  it('POSTs /train-winner (no body) and invalidates the run query', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ selection_id: 'sel_c', model_type: 'naive', model_path: 'p', is_override: false, override_warning: null }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useTrainWinner('sel_c'), {
      wrapper: makeWrapper(makeClient()),
    })
    await act(async () => {
      result.current.mutate()
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const call = fetchMock.mock.calls[0]!
    expect(String(call[0])).toContain('/model-selection/sel_c/train-winner')
    expect((call[1] as RequestInit).method).toBe('POST')
  })
})

describe('useTrainSelected', () => {
  it('POSTs /train-selected with the override body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ selection_id: 'sel_c', model_type: 'seasonal_naive', model_path: 'p', is_override: true, override_warning: 'w' }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useTrainSelected('sel_c'), {
      wrapper: makeWrapper(makeClient()),
    })
    await act(async () => {
      result.current.mutate({ model_type: 'seasonal_naive', override_reason: 'domain' })
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const call = fetchMock.mock.calls[0]!
    expect(String(call[0])).toContain('/model-selection/sel_c/train-selected')
    expect((call[1] as RequestInit).method).toBe('POST')
    expect(String((call[1] as RequestInit).body)).toContain('seasonal_naive')
  })
})

describe('usePredictWinner', () => {
  it('POSTs /predict with the decision params body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ selection_id: 'sel_c', forecast: { points: [], total_demand: 0, average_demand: 0, horizon: 14 }, decision: null }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => usePredictWinner('sel_c'), {
      wrapper: makeWrapper(makeClient()),
    })
    await act(async () => {
      result.current.mutate({ lead_time_days: 7, service_level: 0.95 })
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const call = fetchMock.mock.calls[0]!
    expect(String(call[0])).toContain('/model-selection/sel_c/predict')
    expect((call[1] as RequestInit).method).toBe('POST')
  })
})

describe('usePromoteChampion', () => {
  it('POSTs /promote with the promote body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ selection_id: 'sel_c', alias_name: 'champion-x', run_id: 'r', run_status: 'success', model_type: 'naive', is_override: false, promoted_at: '2026-06-01T00:00:00Z' }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => usePromoteChampion('sel_c'), {
      wrapper: makeWrapper(makeClient()),
    })
    await act(async () => {
      result.current.mutate({ alias_name: 'champion-x', approved_by: 'gabor' })
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const call = fetchMock.mock.calls[0]!
    expect(String(call[0])).toContain('/model-selection/sel_c/promote')
    expect((call[1] as RequestInit).method).toBe('POST')
    expect(String((call[1] as RequestInit).body)).toContain('champion-x')
  })
})
