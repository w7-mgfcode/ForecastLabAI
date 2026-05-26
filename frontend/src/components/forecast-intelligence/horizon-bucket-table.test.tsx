import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { HorizonBucketTable } from './horizon-bucket-table'

afterEach(cleanup)

const FOUR_BUCKETS: Record<string, Record<string, number>> = {
  h_29_plus: { mae: 12.3, wape: 0.41 },
  h_1_7: { mae: 4.2, wape: 0.12 },
  h_15_28: { mae: 9.5, wape: 0.31 },
  h_8_14: { mae: 6.8, wape: 0.22 },
}

describe('HorizonBucketTable', () => {
  it('renders empty state for undefined bucketed payload', () => {
    render(<HorizonBucketTable bucketed={undefined} metric="mae" />)
    expect(screen.getByTestId('horizon-bucket-table-empty')).toBeTruthy()
  })

  it('renders empty state for empty bucketed dict', () => {
    render(<HorizonBucketTable bucketed={{}} metric="wape" />)
    expect(screen.getByTestId('horizon-bucket-table-empty')).toBeTruthy()
  })

  it('renders all four buckets in canonical order', () => {
    const { container } = render(
      <HorizonBucketTable bucketed={FOUR_BUCKETS} metric="mae" />,
    )
    const rows = container.querySelectorAll('[data-testid^="horizon-bucket-row-"]')
    expect(rows.length).toBe(4)
    expect(rows[0]?.getAttribute('data-testid')).toBe(
      'horizon-bucket-row-h_1_7',
    )
    expect(rows[1]?.getAttribute('data-testid')).toBe(
      'horizon-bucket-row-h_8_14',
    )
    expect(rows[2]?.getAttribute('data-testid')).toBe(
      'horizon-bucket-row-h_15_28',
    )
    expect(rows[3]?.getAttribute('data-testid')).toBe(
      'horizon-bucket-row-h_29_plus',
    )
  })

  it('renders dash when the picked metric is missing in a bucket', () => {
    const partial: Record<string, Record<string, number>> = {
      h_1_7: { wape: 0.1 },
    }
    render(<HorizonBucketTable bucketed={partial} metric="rmse" />)
    const row = screen.getByTestId('horizon-bucket-row-h_1_7')
    expect(row.textContent).toContain('—')
  })

  it('appends unknown bucket ids at the end', () => {
    const withUnknown: Record<string, Record<string, number>> = {
      h_extra: { mae: 1.0 },
      h_1_7: { mae: 2.0 },
    }
    const { container } = render(
      <HorizonBucketTable bucketed={withUnknown} metric="mae" />,
    )
    const rows = container.querySelectorAll('[data-testid^="horizon-bucket-row-"]')
    expect(rows[0]?.getAttribute('data-testid')).toBe(
      'horizon-bucket-row-h_1_7',
    )
    expect(rows[1]?.getAttribute('data-testid')).toBe(
      'horizon-bucket-row-h_extra',
    )
  })
})
