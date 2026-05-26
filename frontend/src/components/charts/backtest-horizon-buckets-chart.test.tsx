import { afterEach, beforeAll, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { BacktestHorizonBucketsChart } from './backtest-horizon-buckets-chart'

// Recharts' ResponsiveContainer requires ResizeObserver; jsdom doesn't ship it.
beforeAll(() => {
  if (typeof globalThis.ResizeObserver === 'undefined') {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof globalThis.ResizeObserver
  }
})

afterEach(cleanup)

describe('BacktestHorizonBucketsChart', () => {
  it('renders empty state when bucketed is undefined', () => {
    render(
      <BacktestHorizonBucketsChart bucketed={undefined} metric="wape" />,
    )
    expect(screen.getByTestId('horizon-buckets-chart-empty')).toBeTruthy()
  })

  it('renders empty state for an empty bucketed dict', () => {
    render(<BacktestHorizonBucketsChart bucketed={{}} metric="wape" />)
    expect(screen.getByTestId('horizon-buckets-chart-empty')).toBeTruthy()
  })

  it('renders the chart container when bucketed has data', () => {
    render(
      <BacktestHorizonBucketsChart
        bucketed={{
          h_1_7: { wape: 0.12 },
          h_29_plus: { wape: 0.41 },
        }}
        metric="wape"
      />,
    )
    expect(screen.getByTestId('horizon-buckets-chart')).toBeTruthy()
  })
})
