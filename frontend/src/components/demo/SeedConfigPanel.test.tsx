import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { SeedConfigPanel } from './SeedConfigPanel'
import type { SeedOverrides } from '@/types/api'

// jsdom lacks ResizeObserver; the radix Slider requires it (no vitest setup
// file exists in this project — the stub stays local to this suite).
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = globalThis.ResizeObserver ?? (ResizeObserverStub as never)

afterEach(cleanup)

function openPanel(value: SeedOverrides | null = null, props = {}) {
  const onChange = vi.fn()
  render(<SeedConfigPanel value={value} onChange={onChange} {...props} />)
  fireEvent.click(screen.getByText('Advanced seed config'))
  return onChange
}

describe('SeedConfigPanel', () => {
  it('renders all 7 knob controls when expanded', () => {
    openPanel()
    // 3 int inputs
    for (const label of ['Stores', 'Products', 'Window (days)']) {
      expect(screen.getByLabelText(label)).toBeTruthy()
    }
    // 4 float sliders
    for (const label of [
      'Sparsity',
      'Promotion intensity',
      'Stockout intensity',
      'Noise sigma',
    ]) {
      expect(screen.getAllByLabelText(label).length).toBeGreaterThan(0)
    }
  })

  it('emits a sparse object containing only the touched knob', () => {
    const onChange = openPanel()
    fireEvent.change(screen.getByLabelText('Stores'), { target: { value: '8' } })
    expect(onChange).toHaveBeenCalledWith({ stores: 8 })
  })

  it('merges a new knob into the existing sparse object', () => {
    const onChange = openPanel({ stores: 8 })
    fireEvent.change(screen.getByLabelText('Products'), { target: { value: '20' } })
    expect(onChange).toHaveBeenCalledWith({ stores: 8, products: 20 })
  })

  it('emits null when the last knob is cleared', () => {
    const onChange = openPanel({ stores: 8 })
    fireEvent.change(screen.getByLabelText('Stores'), { target: { value: '' } })
    expect(onChange).toHaveBeenCalledWith(null)
  })

  it('emits null via the Clear overrides button', () => {
    const onChange = openPanel({ stores: 8, noise_sigma: 0.25 })
    fireEvent.click(screen.getByText('Clear overrides'))
    expect(onChange).toHaveBeenCalledWith(null)
  })

  it('disables every control when disabled', () => {
    openPanel({ stores: 8 }, { disabled: true })
    expect((screen.getByLabelText('Stores') as HTMLInputElement).disabled).toBe(true)
    expect((screen.getByLabelText('Products') as HTMLInputElement).disabled).toBe(true)
  })

  it('locks only the window control when windowLocked (holiday_rush)', () => {
    openPanel(null, { windowLocked: true })
    expect((screen.getByLabelText('Window (days)') as HTMLInputElement).disabled).toBe(true)
    expect((screen.getByLabelText('Stores') as HTMLInputElement).disabled).toBe(false)
    expect(screen.getByText('pinned window (holiday_rush)')).toBeTruthy()
  })

  it('shows the NaN-WAPE caveat at high stockout intensity', () => {
    openPanel({ stockout_intensity: 0.4 })
    expect(
      screen.getByText(/can legitimately fail the backtest/i)
    ).toBeTruthy()
  })

  it('hides the caveat at tame values', () => {
    openPanel({ stockout_intensity: 0.1, sparsity: 0.2 })
    expect(screen.queryByText(/can legitimately fail the backtest/i)).toBeNull()
  })

  it('echoes the live summary of set knobs', () => {
    openPanel({ stores: 8, products: 20, promotion_intensity: 0.3 })
    expect(screen.getByText('8 stores · 20 products · promo 0.30')).toBeTruthy()
  })
})
