import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { ScopeSelector } from './ScopeSelector'

afterEach(cleanup)

vi.mock('@/hooks/use-stores', () => ({
  useStores: () => ({
    data: {
      stores: [
        {
          id: 12,
          code: 'S012',
          name: 'Riverside',
          region: 'North',
          city: null,
          store_type: 'supermarket',
          created_at: '',
          updated_at: '',
        },
        {
          id: 13,
          code: 'S013',
          name: 'Hilltop',
          region: 'South',
          city: null,
          store_type: 'express',
          created_at: '',
          updated_at: '',
        },
      ],
    },
    isLoading: false,
  }),
}))

vi.mock('@/hooks/use-products', () => ({
  useProducts: () => ({
    data: {
      products: [
        {
          id: 47,
          sku: 'SKU-047',
          name: 'Oat Milk',
          category: 'Dairy',
          brand: 'BrandA',
          base_price: null,
          base_cost: null,
          created_at: '',
          updated_at: '',
        },
      ],
    },
    isLoading: false,
  }),
}))

vi.mock('@/hooks/use-seeder', () => ({
  useSeederStatus: () => ({
    data: {
      date_range_start: '2026-01-01',
      date_range_end: '2026-03-31',
    },
  }),
}))

describe('ScopeSelector', () => {
  it('renders the two dropdowns with auto-discover placeholders', () => {
    render(<ScopeSelector value={null} onChange={() => undefined} />)
    expect(screen.getByText('Auto-discover first store')).toBeTruthy()
    expect(screen.getByText('Auto-discover first product')).toBeTruthy()
    // No preview card while nothing is selected.
    expect(screen.queryByText('Focus pair')).toBeNull()
  })

  it('previews the selected pair with names, traits, and the seeded window', () => {
    render(
      <ScopeSelector value={{ store_id: 12, product_id: 47 }} onChange={() => undefined} />
    )
    expect(screen.getByText('Focus pair')).toBeTruthy()
    expect(screen.getByText('S012 · Riverside (North, supermarket)')).toBeTruthy()
    expect(screen.getByText('SKU-047 · Oat Milk (Dairy, BrandA)')).toBeTruthy()
    expect(screen.getByText(/2026-01-01 → 2026-03-31/)).toBeTruthy()
  })

  it('falls back to raw ids when the pair is not in the loaded page', () => {
    render(
      <ScopeSelector value={{ store_id: 999, product_id: 888 }} onChange={() => undefined} />
    )
    expect(screen.getByText('store #999')).toBeTruthy()
    expect(screen.getByText('product #888')).toBeTruthy()
  })

  it('clears the selection via the Clear focus button', () => {
    const onChange = vi.fn()
    render(<ScopeSelector value={{ store_id: 12, product_id: 47 }} onChange={onChange} />)
    fireEvent.click(screen.getByText('Clear focus'))
    expect(onChange).toHaveBeenCalledWith(null)
  })

  it('hides the Clear button and disables triggers when disabled', () => {
    render(
      <ScopeSelector value={{ store_id: 12, product_id: 47 }} onChange={() => undefined} disabled />
    )
    const storeTrigger = screen.getByLabelText('Focus store') as HTMLButtonElement
    expect(storeTrigger.disabled).toBe(true)
    expect((screen.getByText('Clear focus') as HTMLButtonElement).disabled).toBe(true)
  })
})
