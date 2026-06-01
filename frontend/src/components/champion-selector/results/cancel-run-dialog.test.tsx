import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { CancelRunDialog } from './cancel-run-dialog'

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
})

afterEach(cleanup)

describe('CancelRunDialog', () => {
  it('confirms cancellation via the AlertDialog', () => {
    const onConfirm = vi.fn()
    render(<CancelRunDialog onConfirm={onConfirm} />)
    fireEvent.click(screen.getByTestId('cancel-run-trigger'))
    fireEvent.click(screen.getByTestId('cancel-run-confirm'))
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('disables the trigger while cancelling', () => {
    render(<CancelRunDialog onConfirm={() => {}} isCancelling />)
    const trigger = screen.getByTestId('cancel-run-trigger') as HTMLButtonElement
    expect(trigger.disabled).toBe(true)
  })
})
