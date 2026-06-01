import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { SearchableEntitySelect, type SearchableEntityItem } from './searchable-entity-select'

// Radix Popover positions its content with Popper, which needs ResizeObserver
// + a couple of layout APIs jsdom lacks. Polyfill them locally (the repo has no
// vitest setup file) so the popover can open in the test environment.
beforeAll(() => {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal('ResizeObserver', ResizeObserverStub)
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = () => false
  }
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => {}
  }
})

afterEach(cleanup)

const ITEMS: SearchableEntityItem[] = [
  { id: 7, primary: 'S001 · Downtown', secondary: 'North' },
  { id: 12, primary: 'S002 · Airport', secondary: 'West' },
  { id: 99, primary: 'S003 · Suburb', secondary: 'East' },
]

describe('SearchableEntitySelect', () => {
  it('shows the placeholder when nothing is selected', () => {
    render(
      <SearchableEntitySelect
        items={ITEMS}
        value={null}
        onChange={() => {}}
        placeholder="Pick a store…"
      />,
    )
    expect(screen.getByText('Pick a store…')).toBeTruthy()
  })

  it('filters the list client-side and selects an option on click', () => {
    const onChange = vi.fn()
    render(
      <SearchableEntitySelect items={ITEMS} value={null} onChange={onChange} />,
    )
    fireEvent.click(screen.getByTestId('searchable-entity-select'))

    // All three options visible before filtering.
    expect(screen.getByTestId('searchable-entity-select-option-7')).toBeTruthy()
    expect(screen.getByTestId('searchable-entity-select-option-12')).toBeTruthy()
    expect(screen.getByTestId('searchable-entity-select-option-99')).toBeTruthy()

    // Filter narrows to the Airport row (matches the primary text).
    fireEvent.change(screen.getByTestId('searchable-entity-select-filter'), {
      target: { value: 'airport' },
    })
    expect(screen.queryByTestId('searchable-entity-select-option-7')).toBeNull()
    expect(screen.getByTestId('searchable-entity-select-option-12')).toBeTruthy()

    fireEvent.click(screen.getByTestId('searchable-entity-select-option-12'))
    expect(onChange).toHaveBeenCalledWith(12)
  })

  it('filters on the secondary descriptor too', () => {
    render(
      <SearchableEntitySelect items={ITEMS} value={null} onChange={() => {}} />,
    )
    fireEvent.click(screen.getByTestId('searchable-entity-select'))
    fireEvent.change(screen.getByTestId('searchable-entity-select-filter'), {
      target: { value: 'east' },
    })
    expect(screen.getByTestId('searchable-entity-select-option-99')).toBeTruthy()
    expect(screen.queryByTestId('searchable-entity-select-option-7')).toBeNull()
  })
})
