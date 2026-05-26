import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { ScenarioPicker } from './ScenarioPicker'

afterEach(cleanup)

describe('ScenarioPicker', () => {
  it('renders the current value on the trigger', () => {
    render(<ScenarioPicker value="demo_minimal" onChange={() => undefined} />)
    const trigger = screen.getByRole('combobox')
    expect(trigger).toBeTruthy()
    expect(trigger.textContent ?? '').toContain('demo_minimal')
  })

  it('is disabled when the run is in flight', () => {
    render(<ScenarioPicker value="demo_minimal" onChange={() => undefined} disabled />)
    const trigger = screen.getByRole('combobox') as HTMLButtonElement
    expect(trigger.disabled).toBe(true)
  })

  it('renders the showcase_rich label when that is the selected value', () => {
    render(<ScenarioPicker value="showcase_rich" onChange={() => undefined} />)
    const trigger = screen.getByRole('combobox')
    expect(trigger.textContent ?? '').toContain('showcase_rich')
  })
})
