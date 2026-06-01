import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { ModelDetailDrawer } from './model-detail-drawer'
import type { ModelRankEntry } from '@/types/api'

// Radix Dialog (Sheet) needs these layout APIs in jsdom.
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

const entry: ModelRankEntry = {
  rank: 1,
  model_type: 'regression',
  params: { max_depth: 6 },
  included: true,
  exclusion_reason: null,
  metrics: { wape: 10, smape: 8, mae: 4, rmse: 5, bias: 0.1 },
}

describe('ModelDetailDrawer', () => {
  it('renders the candidate metrics + params when open', () => {
    render(<ModelDetailDrawer entry={entry} open onOpenChange={() => {}} />)
    const drawer = screen.getByTestId('model-detail-drawer')
    expect(drawer.textContent).toContain('regression')
    expect(drawer.textContent).toContain('WAPE')
    expect(drawer.textContent).toContain('max_depth')
  })

  it('renders nothing meaningful when closed', () => {
    render(<ModelDetailDrawer entry={entry} open={false} onOpenChange={() => {}} />)
    expect(screen.queryByTestId('model-detail-drawer')).toBeNull()
  })
})
