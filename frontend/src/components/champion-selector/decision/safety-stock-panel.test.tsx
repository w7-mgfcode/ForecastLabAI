import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { SafetyStockPanel } from './safety-stock-panel'
import type { ForecastDecision } from '@/types/api'

afterEach(cleanup)

const decision: ForecastDecision = {
  method: 'heuristic',
  lead_time_days: 7,
  service_level: 0.95,
  z_value: 1.6449,
  sigma_daily_demand: 1.41,
  expected_demand_over_lead_time: 70,
  safety_stock: 6.13,
  reorder_point: 76.13,
  bias_risk_text: 'bias text',
  caveats: ['heuristic'],
}

function renderPanel(overrides: Partial<Parameters<typeof SafetyStockPanel>[0]> = {}) {
  const props = {
    decision,
    leadTimeDays: 7,
    serviceLevel: 0.95,
    isRecomputing: false,
    onLeadTimeChange: vi.fn(),
    onServiceLevelChange: vi.fn(),
    onRecompute: vi.fn(),
    ...overrides,
  }
  render(<SafetyStockPanel {...props} />)
  return props
}

describe('SafetyStockPanel', () => {
  it('renders the labeled heuristic header and stats', () => {
    renderPanel()
    const text = screen.getByTestId('safety-stock-panel').textContent ?? ''
    expect(text).toContain('Safety stock (heuristic)')
    expect(text).toContain('1.6449')
    expect(text).toContain('6.1')
  })

  it('fires onLeadTimeChange and onRecompute', () => {
    const props = renderPanel()
    fireEvent.change(screen.getByTestId('safety-stock-lead-time'), {
      target: { value: '14' },
    })
    expect(props.onLeadTimeChange).toHaveBeenCalledWith(14)
    fireEvent.click(screen.getByTestId('safety-stock-recompute'))
    expect(props.onRecompute).toHaveBeenCalledOnce()
  })
})
