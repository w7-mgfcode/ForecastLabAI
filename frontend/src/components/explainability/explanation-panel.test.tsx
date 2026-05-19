import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ApiError } from '@/lib/api'
import { ExplanationPanel } from './explanation-panel'
import type { ForecastExplanation } from '@/types/api'

const sampleExplanation: ForecastExplanation = {
  store_id: 1,
  product_id: 2,
  model_type: 'naive',
  method: 'rule_based',
  forecast_value: 42,
  drivers: [
    {
      name: 'last_observation',
      feature_value: 42,
      contribution: 42,
      direction: 'positive',
      description: 'The naive forecast is the last observed value.',
    },
  ],
  reason_codes: [
    { code: 'stockout_constrained', severity: 'warn', detail: '2 stockout days.' },
  ],
  confidence: 'medium',
  caveats: ['Drivers describe correlation, not causation.'],
  agent_summary: 'The naive model forecasts 42 units.',
  as_of_date: '2024-03-01',
  generated_at: '2024-03-01T00:00:00Z',
}

describe('ExplanationPanel', () => {
  it('renders drivers, reason codes, confidence, and caveats', () => {
    render(<ExplanationPanel explanation={sampleExplanation} />)

    expect(screen.getByText('last observation')).toBeTruthy()
    expect(screen.getByText('Positive')).toBeTruthy()
    expect(screen.getByText('medium')).toBeTruthy()
    expect(screen.getByText(/stockout constrained/)).toBeTruthy()
    expect(screen.getByText(/correlation, not causation/)).toBeTruthy()
    expect(screen.getByText(sampleExplanation.agent_summary)).toBeTruthy()
  })

  it('renders a loading state', () => {
    render(<ExplanationPanel isLoading />)
    expect(screen.getByText(/Generating explanation/)).toBeTruthy()
  })

  it('renders a destructive error for an unexpected failure', () => {
    render(<ExplanationPanel error={new Error('boom')} />)
    expect(screen.getByText('boom')).toBeTruthy()
  })

  it('renders a neutral message for a 400 (non-baseline model)', () => {
    const apiError = new ApiError('Explanations are available for baseline models only', 400)
    render(<ExplanationPanel error={apiError} />)
    expect(screen.getByText(/baseline models only/)).toBeTruthy()
  })

  it('shows a no-signals message when there are no reason codes', () => {
    render(
      <ExplanationPanel explanation={{ ...sampleExplanation, reason_codes: [] }} />,
    )
    expect(screen.getByText(/No advisory retail signals/)).toBeTruthy()
  })
})
