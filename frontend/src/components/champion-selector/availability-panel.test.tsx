import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { AvailabilityPanel } from './availability-panel'
import type { PairAvailability } from '@/types/api'

afterEach(cleanup)

function makeAvailability(overrides: Partial<PairAvailability> = {}): PairAvailability {
  return {
    store_id: 7,
    product_id: 12,
    first_sales_date: '2026-01-01',
    last_sales_date: '2026-05-31',
    observed_days: 150,
    expected_calendar_days: 151,
    coverage_ratio: 0.99,
    missing_days: 1,
    zero_sale_days: 4,
    promotion_days: 3,
    average_daily_demand: 9.2,
    status: 'ready',
    recommended_split_config: {
      strategy: 'expanding',
      n_splits: 5,
      min_train_size: 30,
      gap: 0,
      horizon: 14,
    },
    warnings: [],
    ...overrides,
  }
}

describe('AvailabilityPanel', () => {
  it('renders status badge + metric tiles for a ready pair', () => {
    render(
      <AvailabilityPanel
        availability={makeAvailability({ status: 'ready' })}
        isLoading={false}
        isError={false}
      />,
    )
    expect(screen.getByTestId('availability-panel')).toBeTruthy()
    expect(screen.getByTestId('availability-status-badge').textContent).toContain('Ready')
    expect(screen.getByText('Observed days')).toBeTruthy()
    expect(screen.getByText('Avg daily demand')).toBeTruthy()
  })

  it('renders the not-enough-data empty state for an unusable pair', () => {
    render(
      <AvailabilityPanel
        availability={makeAvailability({ status: 'unusable' })}
        isLoading={false}
        isError={false}
      />,
    )
    expect(screen.queryByTestId('availability-panel')).toBeNull()
    expect(screen.getByText('Not enough data to model this pair')).toBeTruthy()
  })

  it('renders an em dash when promotion_days is null', () => {
    render(
      <AvailabilityPanel
        availability={makeAvailability({ promotion_days: null })}
        isLoading={false}
        isError={false}
      />,
    )
    expect(screen.getByText('—')).toBeTruthy()
  })

  it('shows a loading state while assessing', () => {
    render(<AvailabilityPanel isLoading isError={false} />)
    expect(screen.getByText('Assessing data availability…')).toBeTruthy()
  })
})
