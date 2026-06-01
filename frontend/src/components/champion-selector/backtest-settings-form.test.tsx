import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { BacktestSettingsForm } from './backtest-settings-form'
import { splitConfigErrors } from './split-config'
import type { SplitConfig } from '@/types/api'

// Radix Collapsible/Select need a couple of layout APIs jsdom lacks.
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

afterEach(cleanup)

const VALID: SplitConfig = {
  strategy: 'expanding',
  n_splits: 5,
  min_train_size: 30,
  gap: 0,
  horizon: 14,
}

describe('splitConfigErrors', () => {
  it('accepts a valid config', () => {
    expect(splitConfigErrors(VALID)).toEqual([])
  })

  it('flags out-of-range n_splits and gap >= horizon', () => {
    const errors = splitConfigErrors({ ...VALID, n_splits: 1, gap: 14 })
    expect(errors.some((e) => e.includes('Splits'))).toBe(true)
    expect(errors.some((e) => e.includes('Gap must be smaller'))).toBe(true)
  })
})

describe('BacktestSettingsForm', () => {
  it('reveals the advanced split inputs when toggled', () => {
    render(
      <BacktestSettingsForm
        value={VALID}
        rankingMetric="wape"
        forecastHorizon={14}
        onChange={() => {}}
        onRankingMetricChange={() => {}}
      />,
    )
    // Hidden until the collapsible opens.
    expect(screen.queryByTestId('settings-n-splits')).toBeNull()
    fireEvent.click(screen.getByTestId('advanced-toggle'))
    expect(screen.getByTestId('settings-n-splits')).toBeTruthy()
    expect(screen.getByTestId('settings-gap')).toBeTruthy()
  })

  it('renders validation errors for an invalid config', () => {
    render(
      <BacktestSettingsForm
        value={{ ...VALID, n_splits: 1 }}
        rankingMetric="wape"
        forecastHorizon={14}
        onChange={() => {}}
        onRankingMetricChange={() => {}}
      />,
    )
    expect(screen.getByTestId('settings-errors')).toBeTruthy()
    expect(screen.getByText(/Splits must be between 2 and 20/)).toBeTruthy()
  })

  it('"Use recommended split" emits the recommended config (horizon synced)', () => {
    const onChange = vi.fn()
    const recommended: SplitConfig = {
      strategy: 'sliding',
      n_splits: 8,
      min_train_size: 45,
      gap: 1,
      horizon: 7, // intentionally different — must be overridden to forecastHorizon
    }
    render(
      <BacktestSettingsForm
        value={VALID}
        rankingMetric="wape"
        forecastHorizon={14}
        onChange={onChange}
        onRankingMetricChange={() => {}}
        recommended={recommended}
      />,
    )
    fireEvent.click(screen.getByTestId('use-recommended-split'))
    expect(onChange).toHaveBeenCalledWith({
      strategy: 'sliding',
      n_splits: 8,
      min_train_size: 45,
      gap: 1,
      horizon: 14, // synced to forecastHorizon
    })
  })

  it('keeps the horizon input read-only and equal to the forecast horizon', () => {
    render(
      <BacktestSettingsForm
        value={VALID}
        rankingMetric="wape"
        forecastHorizon={21}
        onChange={() => {}}
        onRankingMetricChange={() => {}}
      />,
    )
    const horizon = screen.getByTestId('settings-horizon') as HTMLInputElement
    expect(horizon.value).toBe('21')
    expect(horizon.readOnly).toBe(true)
  })
})
