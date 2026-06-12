import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'
import { WorkspacePanel } from './WorkspacePanel'
import { ApiError } from '@/lib/api'
import type { WorkspaceListItem, WorkspaceListResponse } from '@/types/api'

beforeAll(() => {
  // Radix AlertDialog needs these in jsdom (pattern: cancel-run-dialog.test.tsx).
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

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const baseItem: WorkspaceListItem = {
  workspace_id: 'a'.repeat(32),
  name: 'e4-panel',
  status: 'completed',
  seed: 7,
  scenario: 'demo_minimal',
  reset: false,
  skip_seed: true,
  result_summary: { winner_model_type: 'seasonal_naive' },
  created_at: '2026-06-01T12:00:00Z',
}

let mockResponse: { data: WorkspaceListResponse | undefined; isLoading: boolean } = {
  data: undefined,
  isLoading: false,
}

let mockDeleteResult: { mutate: ReturnType<typeof vi.fn>; isPending: boolean } = {
  mutate: vi.fn(),
  isPending: false,
}

vi.mock('@/hooks/use-workspaces', () => ({
  useWorkspaces: () => mockResponse,
  useDeleteWorkspace: () => mockDeleteResult,
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

function renderPanel(props: Partial<Parameters<typeof WorkspacePanel>[0]> = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <WorkspacePanel
        onLoad={() => {}}
        onReplay={() => {}}
        isRunning={false}
        lastWorkspaceId={null}
        {...props}
      />
    </QueryClientProvider>,
  )
}

describe('WorkspacePanel', () => {
  it('renders the discoverable empty state (panel never hidden)', () => {
    mockResponse = { data: { workspaces: [], total: 0 }, isLoading: false }
    const { container } = renderPanel()
    expect(container.textContent).toContain('Saved workspaces')
    expect(container.textContent).toContain('No saved workspaces yet')
  })

  it('renders a workspace row with name, scenario, seed, status, and winner', () => {
    mockResponse = { data: { workspaces: [baseItem], total: 1 }, isLoading: false }
    const { container } = renderPanel()
    expect(container.textContent).toContain('e4-panel')
    expect(container.textContent).toContain('demo_minimal')
    expect(container.textContent).toContain('seed 7')
    expect(container.textContent).toContain('COMPLETED')
    expect(container.textContent).toContain('winner seasonal_naive')
    // No destructive badge on a reset=false row.
    expect(container.textContent).not.toContain('DESTRUCTIVE')
  })

  it('shows the destructive badge on reset=true rows', () => {
    mockResponse = {
      data: { workspaces: [{ ...baseItem, reset: true }], total: 1 },
      isLoading: false,
    }
    const { container } = renderPanel()
    expect(container.textContent).toContain('DESTRUCTIVE')
  })

  it('falls back to the workspace_id slice when the row is unnamed', () => {
    mockResponse = {
      data: { workspaces: [{ ...baseItem, name: null }], total: 1 },
      isLoading: false,
    }
    const { container } = renderPanel()
    expect(container.textContent).toContain('aaaaaaaa')
  })

  it('invokes onLoad / onReplay with the list item', () => {
    mockResponse = { data: { workspaces: [baseItem], total: 1 }, isLoading: false }
    const onLoad = vi.fn()
    const onReplay = vi.fn()
    const { container } = renderPanel({ onLoad, onReplay })
    const buttons = Array.from(container.querySelectorAll('button'))
    fireEvent.click(buttons.find((b) => (b.textContent ?? '').includes('Load'))!)
    expect(onLoad).toHaveBeenCalledWith(baseItem)
    fireEvent.click(buttons.find((b) => (b.textContent ?? '').includes('Replay'))!)
    expect(onReplay).toHaveBeenCalledWith(baseItem)
  })

  it('disables both actions while a run is in flight', () => {
    mockResponse = { data: { workspaces: [baseItem], total: 1 }, isLoading: false }
    const { container } = renderPanel({ isRunning: true })
    const buttons = Array.from(container.querySelectorAll('button'))
    expect(buttons.length).toBeGreaterThanOrEqual(2)
    expect(buttons.every((b) => b.disabled)).toBe(true)
  })
})

describe('WorkspacePanel — delete', () => {
  function openDeleteDialog() {
    mockResponse = { data: { workspaces: [baseItem], total: 1 }, isLoading: false }
    mockDeleteResult = { mutate: vi.fn(), isPending: false }
    const result = renderPanel({ onDeleted: vi.fn() })
    fireEvent.click(screen.getByLabelText('Delete workspace e4-panel'))
    return result
  }

  it('renders a Delete action for each saved workspace row', () => {
    mockResponse = { data: { workspaces: [baseItem], total: 1 }, isLoading: false }
    const { container } = renderPanel()
    const buttons = Array.from(container.querySelectorAll('button'))
    expect(buttons.some((b) => (b.textContent ?? '').includes('Delete'))).toBe(true)
  })

  it('shows a confirmation whose copy makes metadata-only deletion clear', () => {
    openDeleteDialog()
    // The mutation must not fire before confirmation.
    expect(mockDeleteResult.mutate).not.toHaveBeenCalled()
    // Radix renders the dialog in a portal — read the whole document.
    const copy = document.body.textContent ?? ''
    expect(copy).toContain('Delete workspace "e4-panel"?')
    expect(copy).toContain('only the saved workspace record')
    expect(copy).toContain('NOT deleted')
  })

  it('confirming deletes the row and notifies the page on success', () => {
    const onDeleted = vi.fn()
    mockResponse = { data: { workspaces: [baseItem], total: 1 }, isLoading: false }
    mockDeleteResult = { mutate: vi.fn(), isPending: false }
    renderPanel({ onDeleted })
    fireEvent.click(screen.getByLabelText('Delete workspace e4-panel'))
    fireEvent.click(screen.getByTestId('workspace-delete-confirm'))

    expect(mockDeleteResult.mutate).toHaveBeenCalledTimes(1)
    const [workspaceId, options] = mockDeleteResult.mutate.mock.calls[0] as [
      string,
      { onSuccess: () => void; onError: (error: unknown) => void },
    ]
    expect(workspaceId).toBe(baseItem.workspace_id)

    // Success path: the page hook is told so it can drop a loaded workspace;
    // the list refetch itself lives in useDeleteWorkspace (hook test).
    options.onSuccess()
    expect(onDeleted).toHaveBeenCalledWith(baseItem.workspace_id)
    expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('were kept'))
  })

  it('cancelling the dialog never fires the mutation', () => {
    openDeleteDialog()
    fireEvent.click(screen.getByText('Keep workspace'))
    expect(mockDeleteResult.mutate).not.toHaveBeenCalled()
  })

  it('surfaces a failed delete via the error toast', () => {
    openDeleteDialog()
    fireEvent.click(screen.getByTestId('workspace-delete-confirm'))
    const [, options] = mockDeleteResult.mutate.mock.calls[0] as [
      string,
      { onSuccess: () => void; onError: (error: unknown) => void },
    ]
    options.onError(new ApiError('Workspace not found: ' + 'a'.repeat(32), 404))
    expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('Delete failed'))
  })
})
