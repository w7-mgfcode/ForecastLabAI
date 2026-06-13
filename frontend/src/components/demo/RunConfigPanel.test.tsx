import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
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

// A catalog with one DISABLED opt-in model (lightgbm) — the picker must hide it.
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
      description: 'baseline',
      enabled: true,
    },
    {
      model_type: 'lightgbm',
      label: 'LightGBM',
      family: 'tree',
      feature_aware: true,
      requires_extra: true,
      default_params: {},
      supports_auto_predict: false,
      description: 'opt-in',
      enabled: false,
    },
  ],
  default_candidate_model_types: ['naive'],
}

vi.mock('@/hooks/use-model-selection', () => ({
  useModelCatalog: () => ({ data: CATALOG, isLoading: false, isError: false, error: null }),
}))

import { RunConfigPanel } from './RunConfigPanel'
import { DEFAULT_BACKTEST, DEFAULT_TRAIN_MODELS } from './run-config-utils'

afterEach(cleanup)

function renderPanel(overrides: Partial<React.ComponentProps<typeof RunConfigPanel>> = {}) {
  const onSelectionChange = vi.fn()
  const onBacktestChange = vi.fn()
  render(
    <RunConfigPanel
      scenario="demo_minimal"
      selection={['naive']}
      onSelectionChange={onSelectionChange}
      backtest={{ ...DEFAULT_BACKTEST }}
      onBacktestChange={onBacktestChange}
      {...overrides}
    />,
  )
  // The panel is collapsed by default; open it to render the inner controls.
  fireEvent.click(screen.getByTestId('run-config-toggle'))
  return { onSelectionChange, onBacktestChange }
}

describe('RunConfigPanel', () => {
  it('hides opt-in models whose flag is off (enabled=false)', () => {
    renderPanel()
    expect(screen.getByTestId('candidate-model-naive')).toBeTruthy()
    expect(screen.queryByTestId('candidate-model-lightgbm')).toBeNull()
  })

  it('appends prophet_like (V2) to the preview only on showcase_rich', () => {
    renderPanel({ scenario: 'showcase_rich', selection: ['naive'] })
    expect(screen.getByTestId('preview-chip-naive')).toBeTruthy()
    expect(screen.getByTestId('preview-chip-prophet_like')).toBeTruthy()
  })

  it('does not append prophet_like on demo_minimal', () => {
    renderPanel({ scenario: 'demo_minimal', selection: ['naive'] })
    expect(screen.getByTestId('preview-chip-naive')).toBeTruthy()
    expect(screen.queryByTestId('preview-chip-prophet_like')).toBeNull()
  })

  it('reset restores the default selection + backtest', () => {
    const { onSelectionChange, onBacktestChange } = renderPanel({ selection: ['naive'] })
    fireEvent.click(screen.getByTestId('run-config-reset'))
    expect(onSelectionChange).toHaveBeenCalledWith(DEFAULT_TRAIN_MODELS)
    expect(onBacktestChange).toHaveBeenCalledWith(DEFAULT_BACKTEST)
  })
})
