import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { ForecastChart } from './forecast-chart'
import type { ModelSelectionForecastSummary } from '@/types/api'

// Recharts' ResponsiveContainer needs ResizeObserver in jsdom.
beforeAll(() => {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal('ResizeObserver', ResizeObserverStub)
})

afterEach(cleanup)

const forecast: ModelSelectionForecastSummary = {
  points: [
    { date: '2026-06-01', forecast: 10, lower_bound: 8, upper_bound: 12 },
    { date: '2026-06-02', forecast: 14, lower_bound: 11, upper_bound: 17 },
  ],
  total_demand: 24,
  average_demand: 12,
  horizon: 2,
}

describe('ForecastChart', () => {
  it('renders the chart container from forecast points', () => {
    render(<ForecastChart forecast={forecast} />)
    expect(screen.getByTestId('forecast-chart')).toBeTruthy()
  })
})
