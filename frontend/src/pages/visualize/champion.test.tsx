import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import type { ModelCatalogResponse } from '@/types/api'

// Radix primitives need a couple of layout APIs jsdom lacks.
beforeAll(() => {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal('ResizeObserver', ResizeObserverStub)
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = () => false
  }
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => {}
  }
})

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
      enabled: true,
    },
    {
      model_type: 'regression',
      label: 'Gradient Boosting Regression',
      family: 'tree',
      feature_aware: true,
      requires_extra: false,
      default_params: {},
      supports_auto_predict: false,
      description: 'Histogram gradient boosting.',
      enabled: true,
    },
  ],
  default_candidate_model_types: ['naive', 'regression'],
}

vi.mock('@/hooks/use-stores', () => ({
  useStores: () => ({
    data: { stores: [{ id: 7, code: 'S001', name: 'Downtown', region: 'North', store_type: 'flagship' }] },
    isLoading: false,
  }),
}))
vi.mock('@/hooks/use-products', () => ({
  useProducts: () => ({
    data: { products: [{ id: 12, sku: 'SKU1', name: 'Widget', category: 'tools' }] },
    isLoading: false,
  }),
}))
vi.mock('@/hooks/use-model-selection', () => ({
  useModelCatalog: () => ({
    data: CATALOG,
    isLoading: false,
    isError: false,
    error: null,
    refetch: () => {},
  }),
  usePairAvailability: () => ({
    data: undefined,
    isLoading: false,
    isError: false,
  }),
  // Slice B — inert async hooks (no run in progress for the shell test).
  useSubmitSelectionRun: () => ({ mutate: vi.fn(), isPending: false }),
  useCancelSelectionRun: () => ({ mutate: vi.fn(), isPending: false }),
  useSelectionRun: () => ({ data: undefined, isLoading: false, isError: false }),
}))

import ChampionSelectorPage from './champion'

afterEach(cleanup)

describe('ChampionSelectorPage', () => {
  it('renders the selection shell', () => {
    render(<ChampionSelectorPage />)
    expect(screen.getByText('Champion Selector')).toBeTruthy()
    expect(screen.getByText('1 · Pick a store & product')).toBeTruthy()
    expect(screen.getByText('2 · Data availability')).toBeTruthy()
    expect(screen.getByText('3 · Candidate models')).toBeTruthy()
    expect(screen.getByText('4 · Backtest settings')).toBeTruthy()
  })

  it('drives candidate cards from the backend catalog', () => {
    render(<ChampionSelectorPage />)
    expect(screen.getByTestId('candidate-model-naive')).toBeTruthy()
    expect(screen.getByTestId('candidate-model-regression')).toBeTruthy()
  })

  it('pre-selects the catalog default candidate models', async () => {
    render(<ChampionSelectorPage />)
    // The seeding effect selects the default two models.
    await waitFor(() =>
      expect(screen.getByText('2 of 10 selected')).toBeTruthy(),
    )
  })

  it('renders the availability empty state until a pair is chosen', () => {
    render(<ChampionSelectorPage />)
    expect(screen.getByText('Pick a store and product')).toBeTruthy()
  })

  it('keeps the Run comparison CTA disabled and issues no POST', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    render(<ChampionSelectorPage />)
    const cta = screen.getByTestId('run-comparison-cta') as HTMLButtonElement
    expect(cta.disabled).toBe(true)
    // The page itself issues no network calls (the hooks are mocked); in
    // particular it never POSTs to /model-selection/run.
    expect(fetchMock).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })
})
