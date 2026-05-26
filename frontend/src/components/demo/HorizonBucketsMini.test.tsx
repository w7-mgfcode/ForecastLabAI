import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { HorizonBucketsMini } from './HorizonBucketsMini'

afterEach(cleanup)

describe('HorizonBucketsMini', () => {
  it('renders a row per known bucket in canonical order', () => {
    const bucketed = {
      h_8_14: { wape: 0.22, mae: 1.5 },
      h_1_7: { wape: 0.12, mae: 0.9 },
    }
    render(<HorizonBucketsMini bucketed={bucketed} />)
    const cells = screen.getAllByText(/Days/)
    expect(cells.length).toBe(2)
    expect(cells[0]?.textContent).toContain('Days 1-7')
    expect(cells[1]?.textContent).toContain('Days 8-14')
  })

  it('shows the picked metric value (mae)', () => {
    const bucketed = {
      h_1_7: { wape: 0.12, mae: 0.9 },
    }
    render(<HorizonBucketsMini bucketed={bucketed} metric="mae" />)
    expect(screen.getByText('0.9000')).toBeTruthy()
  })

  it('renders the empty-state when no buckets are present', () => {
    render(<HorizonBucketsMini bucketed={{}} />)
    expect(screen.getByText('No horizon-bucket metrics available')).toBeTruthy()
  })

  it('shows n/a when the chosen metric is missing for a bucket', () => {
    const bucketed = {
      h_1_7: { mae: 0.9 },
    }
    render(<HorizonBucketsMini bucketed={bucketed} metric="wape" />)
    expect(screen.getByText('n/a')).toBeTruthy()
  })
})
