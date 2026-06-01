import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { BusinessInterpretationPanel } from './business-interpretation-panel'
import type { ForecastDecision } from '@/types/api'

afterEach(cleanup)

const decision: ForecastDecision = {
  method: 'heuristic',
  lead_time_days: 7,
  service_level: 0.95,
  z_value: 1.6449,
  sigma_daily_demand: 1.4,
  expected_demand_over_lead_time: 70,
  safety_stock: 6.1,
  reorder_point: 76.1,
  bias_risk_text: 'Positive bias means the model under-forecasts (risk of stockouts).',
  caveats: ['Safety stock is a deterministic heuristic.'],
}

const businessSummary = {
  headline: 'Recommended model: naive (high confidence).',
  winner: { model_type: 'naive', summary: 'WAPE 10.0%' },
  comparison: { lead_text: '15% lower WAPE than the runner-up' },
  data_notes: ['Observed 120 of 120 calendar days.'],
}

describe('BusinessInterpretationPanel', () => {
  it('renders the headline, expected demand, and bias risk', () => {
    render(
      <BusinessInterpretationPanel businessSummary={businessSummary} decision={decision} />,
    )
    const text = screen.getByTestId('business-interpretation-panel').textContent ?? ''
    expect(text).toContain('Recommended model: naive')
    expect(screen.getByTestId('business-expected-demand').textContent).toContain('70.0')
    expect(screen.getByTestId('business-bias-risk').textContent).toContain(
      'under-forecasts',
    )
  })

  it('falls back to the bias explanation when no decision is present', () => {
    render(<BusinessInterpretationPanel businessSummary={businessSummary} decision={null} />)
    expect(
      screen.getByText(/Positive bias means the model under-forecasts/),
    ).toBeTruthy()
  })
})
