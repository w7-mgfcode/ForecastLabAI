import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { ForecastSummaryCard } from './forecast-summary-card'
import type { ModelSelectionForecastSummary } from '@/types/api'

afterEach(cleanup)

const forecast: ModelSelectionForecastSummary = {
  points: [],
  total_demand: 140,
  average_demand: 10,
  horizon: 14,
  peak_date: '2026-06-02',
  peak_demand: 25,
  low_date: '2026-06-03',
  low_demand: 5,
}

describe('ForecastSummaryCard', () => {
  it('renders total, peak, and low tiles', () => {
    render(<ForecastSummaryCard forecast={forecast} />)
    const text = screen.getByTestId('forecast-summary-card').textContent ?? ''
    expect(text).toContain('140.0')
    expect(text).toContain('25.0')
    expect(text).toContain('2026-06-02')
    expect(text).toContain('14d')
  })

  it('renders an em-dash for null peak/low', () => {
    render(
      <ForecastSummaryCard
        forecast={{ ...forecast, peak_demand: null, low_demand: null }}
      />,
    )
    expect(screen.getByTestId('forecast-summary-card').textContent).toContain('—')
  })
})
