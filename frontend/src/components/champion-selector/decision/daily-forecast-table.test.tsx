import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { DailyForecastTable } from './daily-forecast-table'
import type { ModelSelectionForecastSummary } from '@/types/api'

afterEach(cleanup)

const forecast: ModelSelectionForecastSummary = {
  points: [
    { date: '2026-06-01', forecast: 10.5, lower_bound: 8, upper_bound: 12 },
    { date: '2026-06-02', forecast: 14.2, lower_bound: null, upper_bound: null },
  ],
  total_demand: 24.7,
  average_demand: 12.35,
  horizon: 2,
}

describe('DailyForecastTable', () => {
  it('renders one row per forecast point with the forecast value', () => {
    render(<DailyForecastTable forecast={forecast} />)
    const text = screen.getByTestId('daily-forecast-table').textContent ?? ''
    expect(text).toContain('2026-06-01')
    expect(text).toContain('10.50')
    expect(text).toContain('14.20')
  })
})
