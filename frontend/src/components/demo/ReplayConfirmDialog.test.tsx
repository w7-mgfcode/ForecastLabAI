import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { ReplayConfirmDialog } from './ReplayConfirmDialog'
import { buildReplayRequest } from './replay-request'
import type { WorkspaceListItem } from '@/types/api'

beforeAll(() => {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal('ResizeObserver', ResizeObserverStub)
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const baseItem: WorkspaceListItem = {
  workspace_id: 'a'.repeat(32),
  name: 'replay-me',
  status: 'completed',
  seed: 7,
  scenario: 'demo_minimal',
  reset: false,
  skip_seed: true,
  result_summary: null,
  created_at: '2026-06-01T12:00:00Z',
  archived: false,
  pinned: false,
  tags: [],
  replayed_from_workspace_id: null,
}

function renderDialog(workspace: WorkspaceListItem | null, handlers = {}) {
  const onConfirm = vi.fn()
  const onCancel = vi.fn()
  render(
    <ReplayConfirmDialog
      workspace={workspace}
      requestPreview={workspace ? buildReplayRequest(workspace) : null}
      onConfirm={onConfirm}
      onCancel={onCancel}
      {...handlers}
    />,
  )
  return { onConfirm, onCancel }
}

describe('ReplayConfirmDialog', () => {
  it('renders nothing while no replay is pending', () => {
    renderDialog(null)
    expect(document.body.textContent).not.toContain('Replay workspace')
  })

  it('renders the recorded-vs-sent preview values', () => {
    renderDialog(baseItem)
    const copy = document.body.textContent ?? ''
    expect(copy).toContain('Replay workspace “replay-me”?')
    expect(copy).toContain('seed')
    expect(copy).toContain('7')
    expect(copy).toContain('demo_minimal')
    expect(copy).toContain('keep')
    // replayed_from points at the source row on both columns.
    expect(copy).toContain(baseItem.workspace_id)
    // The verbatim-replay hint for operators who want a different config.
    expect(copy).toContain('Use Load instead')
  })

  it('uses a plain confirm label on a non-destructive replay', () => {
    renderDialog(baseItem)
    const action = screen.getByTestId('replay-confirm')
    expect(action.textContent).toBe('Replay')
    expect(document.body.textContent).not.toContain('WIPES the database')
  })

  it('escalates to destructive copy + label when reset=true', () => {
    renderDialog({ ...baseItem, reset: true })
    expect(document.body.textContent).toContain('WIPES the database')
    const action = screen.getByTestId('replay-confirm')
    expect(action.textContent).toBe('Replay & wipe database')
    expect(action.className).toContain('bg-destructive')
  })

  it('confirm fires onConfirm once; cancel fires onCancel and never confirms', () => {
    const { onConfirm } = renderDialog(baseItem)
    fireEvent.click(screen.getByTestId('replay-confirm'))
    expect(onConfirm).toHaveBeenCalledTimes(1)
    cleanup()
    const second = renderDialog(baseItem)
    fireEvent.click(screen.getByText('Cancel'))
    expect(second.onCancel).toHaveBeenCalledTimes(1)
    expect(second.onConfirm).not.toHaveBeenCalled()
  })

  it('highlights a mismatching row (defensive — verbatim replays match)', () => {
    render(
      <ReplayConfirmDialog
        workspace={baseItem}
        requestPreview={{ ...buildReplayRequest(baseItem), seed: 99 }}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    const mismatched = document.querySelector('td.font-semibold.text-destructive')
    expect(mismatched?.textContent).toBe('99')
  })
})
