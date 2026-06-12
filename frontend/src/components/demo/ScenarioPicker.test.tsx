import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { ScenarioPicker } from './ScenarioPicker'

afterEach(cleanup)

const ALL_PRESETS = [
  'retail_standard',
  'holiday_rush',
  'high_variance',
  'stockout_heavy',
  'new_launches',
  'sparse',
  'demo_minimal',
  'showcase_rich',
] as const

describe('ScenarioPicker', () => {
  it('renders all 8 preset cards with their monospace ids', () => {
    render(<ScenarioPicker value="demo_minimal" onChange={() => undefined} />)
    const cards = screen.getAllByRole('button')
    expect(cards.length).toBe(8)
    for (const preset of ALL_PRESETS) {
      expect(screen.getByText(preset)).toBeTruthy()
    }
  })

  it('fires onChange with the preset value when a card is clicked', () => {
    const onChange = vi.fn()
    render(<ScenarioPicker value="demo_minimal" onChange={onChange} />)
    fireEvent.click(screen.getByText('retail_standard').closest('button')!)
    expect(onChange).toHaveBeenCalledWith('retail_standard')
  })

  it('marks the selected card with aria-pressed=true and all others false', () => {
    render(<ScenarioPicker value="showcase_rich" onChange={() => undefined} />)
    const pressed = screen.getAllByRole('button', { pressed: true })
    expect(pressed.length).toBe(1)
    expect(pressed[0]!.textContent ?? '').toContain('showcase_rich')
    expect(screen.getAllByRole('button', { pressed: false }).length).toBe(7)
  })

  it('disables every card while a run is in flight', () => {
    render(<ScenarioPicker value="demo_minimal" onChange={() => undefined} disabled />)
    const cards = screen.getAllByRole('button') as HTMLButtonElement[]
    expect(cards.length).toBe(8)
    for (const card of cards) {
      expect(card.disabled).toBe(true)
    }
  })

  it('shows the expected-fail caveat on the sparse card', () => {
    render(<ScenarioPicker value="demo_minimal" onChange={() => undefined} />)
    const sparseCard = screen.getByText('sparse').closest('button')!
    expect(sparseCard.textContent ?? '').toContain('expected')
  })

  it('shows the pinned-2024-window caveat on the holiday_rush card', () => {
    render(<ScenarioPicker value="demo_minimal" onChange={() => undefined} />)
    const holidayCard = screen.getByText('holiday_rush').closest('button')!
    expect(holidayCard.textContent ?? '').toContain('2024')
  })
})
