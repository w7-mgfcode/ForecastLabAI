import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { ComparisonCharts } from './comparison-charts'
import type { ModelSelectionChartData } from '@/types/api'

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

const chartData: ModelSelectionChartData = {
  wape_by_model: { regression: 10, naive: 14 },
  bias_by_model: { regression: -0.2, naive: 0.5 },
  fold_stability: { regression: [10, 11] },
  winner_actual_vs_predicted: [
    { dates: ['2026-01-01', '2026-01-02'], actuals: [10, 12], predictions: [9.5, 12.5] },
  ],
}

describe('ComparisonCharts', () => {
  it('renders WAPE + bias bars from chart_data', () => {
    render(<ComparisonCharts chartData={chartData} winnerModelType="regression" />)
    expect(screen.getByTestId('comparison-charts')).toBeTruthy()
    expect(screen.getByTestId('metric-bars-wape-by-model')).toBeTruthy()
    expect(screen.getByTestId('metric-bars-bias-by-model')).toBeTruthy()
    // Winner is starred in the bar list.
    expect(screen.getAllByText('★ regression').length).toBeGreaterThan(0)
  })
})
