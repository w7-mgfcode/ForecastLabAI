import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { ModelFamilyTabs } from './model-family-tabs'

afterEach(cleanup)

describe('ModelFamilyTabs', () => {
  it('renders one tab per family with the current selection marked active', () => {
    render(<ModelFamilyTabs family="tree" onChange={() => {}} />)
    const tree = screen.getByTestId('model-family-tab-tree')
    expect(tree.getAttribute('data-state')).toBe('active')
    expect(screen.getByTestId('model-family-tab-baseline')).toBeTruthy()
    expect(screen.getByTestId('model-family-tab-additive')).toBeTruthy()
  })

  it('emits onChange with the picked family on pointer interaction', () => {
    // Radix Tabs trigger switches on pointerDown rather than click in jsdom.
    const onChange = vi.fn()
    render(<ModelFamilyTabs family="baseline" onChange={onChange} />)
    const target = screen.getByTestId('model-family-tab-additive')
    fireEvent.pointerDown(target, { button: 0, ctrlKey: false })
    fireEvent.mouseDown(target, { button: 0 })
    fireEvent.click(target)
    expect(onChange).toHaveBeenCalledWith('additive')
  })

  it('does not emit onChange when disabled', () => {
    const onChange = vi.fn()
    render(<ModelFamilyTabs family="baseline" onChange={onChange} disabled />)
    const target = screen.getByTestId('model-family-tab-tree')
    fireEvent.pointerDown(target, { button: 0 })
    fireEvent.click(target)
    expect(onChange).not.toHaveBeenCalled()
  })
})
