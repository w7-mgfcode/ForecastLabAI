import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'
import { WorkspaceEditDialog } from './WorkspaceEditDialog'
import type { WorkspaceDetail, WorkspaceListItem } from '@/types/api'

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
  name: 'edit-me',
  status: 'completed',
  seed: 7,
  scenario: 'demo_minimal',
  reset: false,
  skip_seed: true,
  result_summary: null,
  created_at: '2026-06-01T12:00:00Z',
  archived: false,
  pinned: false,
  tags: ['smoke'],
  replayed_from_workspace_id: null,
  seed_overrides: null,
  user_scope: null,
}

let mockDetail: {
  data: Partial<WorkspaceDetail> | undefined
  isSuccess: boolean
  isError: boolean
} = { data: undefined, isSuccess: false, isError: false }

let mockPatchResult: { mutate: ReturnType<typeof vi.fn>; isPending: boolean } = {
  mutate: vi.fn(),
  isPending: false,
}

vi.mock('@/hooks/use-workspaces', () => ({
  useWorkspace: () => mockDetail,
  usePatchWorkspace: () => mockPatchResult,
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

beforeEach(() => {
  mockDetail = {
    data: { ...baseItem, notes: 'old notes' },
    isSuccess: true,
    isError: false,
  }
  mockPatchResult = { mutate: vi.fn(), isPending: false }
})

function renderDialog(workspace: WorkspaceListItem | null = baseItem) {
  const onClose = vi.fn()
  render(<WorkspaceEditDialog workspace={workspace} onClose={onClose} />)
  return { onClose }
}

describe('WorkspaceEditDialog', () => {
  it('renders nothing when closed', () => {
    renderDialog(null)
    expect(document.body.textContent).not.toContain('Edit workspace details')
  })

  it('primes the form from the row + detail notes', () => {
    renderDialog()
    expect((screen.getByLabelText('Name') as HTMLInputElement).value).toBe('edit-me')
    expect((screen.getByLabelText('Notes') as HTMLTextAreaElement).value).toBe('old notes')
    expect(
      (screen.getByLabelText(/Tags/) as HTMLInputElement).value,
    ).toBe('smoke')
  })

  it('disables Save with an inline hint on a pattern violation', () => {
    renderDialog()
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Bad Name!' } })
    expect(document.body.textContent).toContain('Lowercase letters/digits only')
    expect((screen.getByTestId('workspace-edit-save') as HTMLButtonElement).disabled).toBe(true)
    expect(mockPatchResult.mutate).not.toHaveBeenCalled()
  })

  it('sends ONLY dirty fields (partial-update semantics)', () => {
    renderDialog()
    fireEvent.change(screen.getByLabelText(/Tags/), { target: { value: 'smoke, e2' } })
    fireEvent.click(screen.getByTestId('workspace-edit-save'))
    expect(mockPatchResult.mutate).toHaveBeenCalledTimes(1)
    const [payload] = mockPatchResult.mutate.mock.calls[0] as [
      { workspaceId: string; update: Record<string, unknown> },
      unknown,
    ]
    expect(payload.workspaceId).toBe(baseItem.workspace_id)
    expect(payload.update).toEqual({ tags: ['smoke', 'e2'] })
  })

  it('clearing the name sends an explicit null', () => {
    renderDialog()
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: '' } })
    fireEvent.click(screen.getByTestId('workspace-edit-save'))
    const [payload] = mockPatchResult.mutate.mock.calls[0] as [
      { update: Record<string, unknown> },
      unknown,
    ]
    expect(payload.update).toEqual({ name: null })
  })

  it('a clean save (no changes) just closes without a mutation', () => {
    const { onClose } = renderDialog()
    fireEvent.click(screen.getByTestId('workspace-edit-save'))
    expect(mockPatchResult.mutate).not.toHaveBeenCalled()
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('success toasts and closes; failure toasts an error', () => {
    const { onClose } = renderDialog()
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'renamed' } })
    fireEvent.click(screen.getByTestId('workspace-edit-save'))
    const [, options] = mockPatchResult.mutate.mock.calls[0] as [
      unknown,
      { onSuccess: () => void; onError: (error: unknown) => void },
    ]
    options.onSuccess()
    expect(toast.success).toHaveBeenCalledWith('Workspace updated.')
    expect(onClose).toHaveBeenCalled()
    options.onError(new Error('boom'))
    expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('Update failed'))
  })
})
