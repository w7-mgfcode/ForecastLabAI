import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { DemoBacktestSettingsForm } from './DemoBacktestSettingsForm'
import { DEFAULT_BACKTEST } from './run-config-utils'
import type { DemoBacktestConfig } from '@/types/api'

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

afterEach(cleanup)

describe('DemoBacktestSettingsForm', () => {
  it('edits the horizon and calls onChange', () => {
    const onChange = vi.fn()
    render(
      <DemoBacktestSettingsForm
        value={{ ...DEFAULT_BACKTEST }}
        scenario="demo_minimal"
        onChange={onChange}
      />,
    )
    fireEvent.change(screen.getByTestId('demo-settings-horizon'), {
      target: { value: '21' },
    })
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ horizon: 21 } satisfies Partial<DemoBacktestConfig>),
    )
  })

  it('shows the split-fit warning when the split exceeds the window', () => {
    render(
      <DemoBacktestSettingsForm
        value={{ ...DEFAULT_BACKTEST, horizon: 28, n_splits: 5, min_train_size: 60 }}
        scenario="demo_minimal"
        onChange={() => {}}
      />,
    )
    expect(screen.getByTestId('demo-split-fit-warning')).toBeTruthy()
  })

  it('hides the warning for a fitting split', () => {
    render(
      <DemoBacktestSettingsForm
        value={{ ...DEFAULT_BACKTEST }}
        scenario="demo_minimal"
        onChange={() => {}}
      />,
    )
    expect(screen.queryByTestId('demo-split-fit-warning')).toBeNull()
  })

  it('surfaces a split validation error (gap >= horizon)', () => {
    render(
      <DemoBacktestSettingsForm
        value={{ ...DEFAULT_BACKTEST, horizon: 5, gap: 5 }}
        scenario="showcase_rich"
        onChange={() => {}}
      />,
    )
    expect(screen.getByTestId('demo-settings-errors')).toBeTruthy()
  })
})
