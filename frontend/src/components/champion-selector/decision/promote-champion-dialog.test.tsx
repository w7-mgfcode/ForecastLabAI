import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { PromoteChampionDialog } from './promote-champion-dialog'

afterEach(cleanup)

function renderDialog(overrides: Partial<Parameters<typeof PromoteChampionDialog>[0]> = {}) {
  const props = {
    open: true,
    onOpenChange: vi.fn(),
    isOverride: false,
    isPromoting: false,
    promoteError: null,
    promotedAlias: null,
    onConfirm: vi.fn(),
    ...overrides,
  }
  render(<PromoteChampionDialog {...props} />)
  return props
}

describe('PromoteChampionDialog', () => {
  it('keeps confirm disabled until alias + approver are valid', () => {
    renderDialog()
    expect(screen.getByTestId('promote-confirm-action').hasAttribute('disabled')).toBe(true)
    fireEvent.change(screen.getByTestId('promote-alias-input'), {
      target: { value: 'champion-x' },
    })
    fireEvent.change(screen.getByTestId('promote-approver-input'), {
      target: { value: 'gabor' },
    })
    expect(screen.getByTestId('promote-confirm-action').hasAttribute('disabled')).toBe(false)
  })

  it('flags an invalid alias name', () => {
    renderDialog()
    fireEvent.change(screen.getByTestId('promote-alias-input'), {
      target: { value: 'Bad Alias' },
    })
    expect(screen.getByTestId('promote-alias-error')).toBeTruthy()
  })

  it('requires the ack checkbox for a non-recommended (override) model', () => {
    renderDialog({ isOverride: true })
    fireEvent.change(screen.getByTestId('promote-alias-input'), {
      target: { value: 'champion-x' },
    })
    fireEvent.change(screen.getByTestId('promote-approver-input'), {
      target: { value: 'gabor' },
    })
    // still disabled until the ack is checked
    expect(screen.getByTestId('promote-confirm-action').hasAttribute('disabled')).toBe(true)
    fireEvent.click(screen.getByTestId('promote-ack-checkbox'))
    expect(screen.getByTestId('promote-confirm-action').hasAttribute('disabled')).toBe(false)
  })

  it('calls onConfirm with the promote body', () => {
    const props = renderDialog()
    fireEvent.change(screen.getByTestId('promote-alias-input'), {
      target: { value: 'champion-x' },
    })
    fireEvent.change(screen.getByTestId('promote-approver-input'), {
      target: { value: 'gabor' },
    })
    fireEvent.click(screen.getByTestId('promote-confirm-action'))
    expect(props.onConfirm).toHaveBeenCalledWith({
      alias_name: 'champion-x',
      approved_by: 'gabor',
      acknowledge_non_recommended: false,
    })
  })
})
