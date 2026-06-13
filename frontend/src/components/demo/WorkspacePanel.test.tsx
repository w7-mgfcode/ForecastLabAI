import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'
import { WorkspacePanel } from './WorkspacePanel'
import { ApiError } from '@/lib/api'
import type { WorkspaceListItem, WorkspaceListParams, WorkspaceListResponse } from '@/types/api'

beforeAll(() => {
  // Radix AlertDialog/DropdownMenu need these in jsdom.
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal('ResizeObserver', ResizeObserverStub)
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = () => false
  }
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => {}
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
  archived: false,
  pinned: false,
  tags: [],
  replayed_from_workspace_id: null,
  seed_overrides: null,
  user_scope: null,
  run_config: null,
}

const secondItem: WorkspaceListItem = {
  ...baseItem,
  workspace_id: 'b'.repeat(32),
  name: 'second',
}

let mockResponse: { data: WorkspaceListResponse | undefined; isLoading: boolean } = {
  data: undefined,
  isLoading: false,
}

let lastListParams: WorkspaceListParams | undefined

let mockDeleteResult: {
  mutate: ReturnType<typeof vi.fn>
  mutateAsync: ReturnType<typeof vi.fn>
  isPending: boolean
} = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }

let mockPatchResult: { mutate: ReturnType<typeof vi.fn>; isPending: boolean } = {
  mutate: vi.fn(),
  isPending: false,
}

let mockExportResult: { mutate: ReturnType<typeof vi.fn>; isPending: boolean } = {
  mutate: vi.fn(),
  isPending: false,
}

const mockNavigate = vi.fn()

vi.mock('@/hooks/use-workspaces', () => ({
  useWorkspaces: (params: WorkspaceListParams) => {
    lastListParams = params
    return mockResponse
  },
  // WorkspaceEditDialog dependencies (mounted closed by the panel).
  useWorkspace: () => ({ data: undefined, isSuccess: false, isError: false }),
  useDeleteWorkspace: () => mockDeleteResult,
  usePatchWorkspace: () => mockPatchResult,
  useExportWorkspace: () => mockExportResult,
}))

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => mockNavigate }
})

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

beforeEach(() => {
  lastListParams = undefined
  mockDeleteResult = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }
  mockPatchResult = { mutate: vi.fn(), isPending: false }
  mockExportResult = { mutate: vi.fn(), isPending: false }
})

function renderPanel(props: Partial<Parameters<typeof WorkspacePanel>[0]> = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <WorkspacePanel
          onLoad={() => {}}
          onRequestReplay={() => {}}
          isRunning={false}
          lastWorkspaceId={null}
          {...props}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** Open a Radix dropdown/select (pattern: model-family-tabs.test.tsx). */
function radixOpen(target: HTMLElement) {
  fireEvent.pointerDown(target, { button: 0, ctrlKey: false })
  fireEvent.mouseDown(target, { button: 0 })
  fireEvent.click(target)
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

  it('renders the custom-config badge only when run_config is set (E4 #410)', () => {
    // Default-config row: no badge.
    mockResponse = { data: { workspaces: [baseItem], total: 1 }, isLoading: false }
    const plain = renderPanel()
    expect(plain.container.querySelector('[data-testid="run-config-summary-badge"]')).toBeNull()
    cleanup()

    // Custom-config row: badge with the compact summary.
    mockResponse = {
      data: {
        workspaces: [
          {
            ...baseItem,
            run_config: {
              train_model_types: ['naive', 'regression', 'prophet_like', 'seasonal_average'],
              backtest: { horizon: 21, n_splits: 4, metric: 'rmse' },
            },
          },
        ],
        total: 1,
      },
      isLoading: false,
    }
    const custom = renderPanel()
    const badge = custom.container.querySelector('[data-testid="run-config-summary-badge"]')
    expect(badge).not.toBeNull()
    expect(badge!.textContent).toContain('4 models')
    expect(badge!.textContent).toContain('rmse')
    expect(badge!.textContent).toContain('4×h21')
  })

  it('invokes onLoad / onRequestReplay with the list item — replay never starts here', () => {
    mockResponse = { data: { workspaces: [baseItem], total: 1 }, isLoading: false }
    const onLoad = vi.fn()
    const onRequestReplay = vi.fn()
    const { container } = renderPanel({ onLoad, onRequestReplay })
    const buttons = Array.from(container.querySelectorAll('button'))
    fireEvent.click(buttons.find((b) => (b.textContent ?? '').includes('Load'))!)
    expect(onLoad).toHaveBeenCalledWith(baseItem)
    fireEvent.click(buttons.find((b) => (b.textContent ?? '').includes('Replay'))!)
    expect(onRequestReplay).toHaveBeenCalledWith(baseItem)
  })

  it('disables row actions while a run is in flight', () => {
    mockResponse = { data: { workspaces: [baseItem], total: 1 }, isLoading: false }
    renderPanel({ isRunning: true })
    const labels = ['Load', 'Replay', 'Export']
    for (const label of labels) {
      const button = screen
        .getAllByRole('button')
        .find((b) => (b.textContent ?? '').includes(label))! as HTMLButtonElement
      expect(button.disabled).toBe(true)
    }
  })
})

describe('WorkspacePanel — E6 export', () => {
  function findExportButton(container: HTMLElement) {
    return Array.from(container.querySelectorAll('button')).find((b) =>
      (b.textContent ?? '').includes('Export')
    )!
  }

  it('renders an Export button per row', () => {
    mockResponse = { data: { workspaces: [baseItem], total: 1 }, isLoading: false }
    const { container } = renderPanel()
    expect(findExportButton(container)).toBeTruthy()
  })

  it('fires the export mutation with the row id and toasts the bundle path', () => {
    mockResponse = { data: { workspaces: [baseItem], total: 1 }, isLoading: false }
    const { container } = renderPanel()
    fireEvent.click(findExportButton(container))

    expect(mockExportResult.mutate).toHaveBeenCalledTimes(1)
    const [workspaceId, options] = mockExportResult.mutate.mock.calls[0] as [
      string,
      { onSuccess: (r: unknown) => void; onError: (error: unknown) => void },
    ]
    expect(workspaceId).toBe(baseItem.workspace_id)

    options.onSuccess({
      workspace_id: baseItem.workspace_id,
      bundle_path: `artifacts/showcase/${baseItem.workspace_id}`,
      bundle_format_version: 1,
      exported_at: '2026-06-12T14:00:00Z',
      files: [
        { path: 'manifest.json', sha256: 'a', size_bytes: 1 },
        { path: 'checksums.sha256', sha256: 'b', size_bytes: 1 },
      ],
      scenario_plans_exported: 0,
      model_runs_referenced: 0,
      unresolved_references: [],
      validated: true,
    })
    expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('Bundle written to'))
    expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('checksums verified'))
  })

  it('notes dangling references in the success toast', () => {
    mockResponse = { data: { workspaces: [baseItem], total: 1 }, isLoading: false }
    const { container } = renderPanel()
    fireEvent.click(findExportButton(container))
    const [, options] = mockExportResult.mutate.mock.calls[0] as [
      string,
      { onSuccess: (r: unknown) => void; onError: (error: unknown) => void },
    ]
    options.onSuccess({
      workspace_id: baseItem.workspace_id,
      bundle_path: `artifacts/showcase/${baseItem.workspace_id}`,
      bundle_format_version: 1,
      exported_at: '2026-06-12T14:00:00Z',
      files: [{ path: 'manifest.json', sha256: 'a', size_bytes: 1 }],
      scenario_plans_exported: 0,
      model_runs_referenced: 0,
      unresolved_references: [{ key: 'scenario_plan_ids', ref_id: 'gone', reason: 'HTTP 404' }],
      validated: true,
    })
    expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('1 unresolved reference'))
  })

  it('surfaces an export failure via the error toast', () => {
    mockResponse = { data: { workspaces: [baseItem], total: 1 }, isLoading: false }
    const { container } = renderPanel()
    fireEvent.click(findExportButton(container))
    const [, options] = mockExportResult.mutate.mock.calls[0] as [
      string,
      { onSuccess: (r: unknown) => void; onError: (error: unknown) => void },
    ]
    options.onError(new ApiError('Export bundle write failed: disk full', 500))
    expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('Export failed'))
  })
})

describe('WorkspacePanel — E2 lifecycle badges + toolbar params', () => {
  it('renders pinned / archived / replay badges', () => {
    mockResponse = {
      data: {
        workspaces: [
          {
            ...baseItem,
            pinned: true,
            archived: true,
            replayed_from_workspace_id: 'c'.repeat(32),
          },
        ],
        total: 1,
      },
      isLoading: false,
    }
    const { container } = renderPanel()
    expect(container.textContent).toContain('archived')
    expect(container.textContent).toContain('replay')
    expect(screen.getByLabelText('Unpin e4-panel')).toBeTruthy()
  })

  it('flows the debounced search into the q list param (min 2 chars)', async () => {
    mockResponse = { data: { workspaces: [baseItem], total: 1 }, isLoading: false }
    renderPanel()
    fireEvent.change(screen.getByLabelText('Search workspaces by name'), {
      target: { value: 'demo' },
    })
    await waitFor(() => expect(lastListParams?.q).toBe('demo'))
  })

  it('flows the show-archived toggle into include_archived', () => {
    mockResponse = { data: { workspaces: [baseItem], total: 1 }, isLoading: false }
    const { container } = renderPanel()
    expect(lastListParams?.include_archived).toBeUndefined()
    const checkbox = Array.from(container.querySelectorAll('button[role="checkbox"]')).find(
      (el) => el.parentElement?.textContent?.includes('Show archived'),
    )!
    fireEvent.click(checkbox)
    expect(lastListParams?.include_archived).toBe(true)
  })

  it('flows the sort select into sort_by/sort_order', () => {
    mockResponse = { data: { workspaces: [baseItem], total: 1 }, isLoading: false }
    renderPanel()
    radixOpen(screen.getByLabelText('Sort workspaces'))
    fireEvent.click(screen.getByText('Name'))
    expect(lastListParams?.sort_by).toBe('name')
    expect(lastListParams?.sort_order).toBe('asc')
  })

  it('clicking a tag chip filters by that tag; the toolbar chip clears it', () => {
    mockResponse = {
      data: { workspaces: [{ ...baseItem, tags: ['smoke'] }], total: 1 },
      isLoading: false,
    }
    renderPanel()
    fireEvent.click(screen.getByLabelText('Filter by tag smoke'))
    expect(lastListParams?.tags).toBe('smoke')
    fireEvent.click(screen.getByLabelText('Clear tag filter smoke'))
    expect(lastListParams?.tags).toBeUndefined()
  })

  it('pin toggle fires the PATCH mutation', () => {
    mockResponse = { data: { workspaces: [baseItem], total: 1 }, isLoading: false }
    renderPanel()
    fireEvent.click(screen.getByLabelText('Pin e4-panel'))
    expect(mockPatchResult.mutate).toHaveBeenCalledWith(
      { workspaceId: baseItem.workspace_id, update: { pinned: true } },
      expect.anything(),
    )
  })

  it('archive action in the dropdown fires the PATCH mutation', () => {
    mockResponse = { data: { workspaces: [baseItem], total: 1 }, isLoading: false }
    renderPanel()
    radixOpen(screen.getByLabelText('More actions for e4-panel'))
    fireEvent.click(screen.getByText('Archive'))
    expect(mockPatchResult.mutate).toHaveBeenCalledWith(
      { workspaceId: baseItem.workspace_id, update: { archived: true } },
      expect.anything(),
    )
  })
})

describe('WorkspacePanel — multi-select', () => {
  function selectBoth() {
    mockResponse = { data: { workspaces: [baseItem, secondItem], total: 2 }, isLoading: false }
    const result = renderPanel({ onDeleted: vi.fn() })
    fireEvent.click(screen.getByLabelText('Select workspace e4-panel'))
    fireEvent.click(screen.getByLabelText('Select workspace second'))
    return result
  }

  it('shows the selection footer with the count', () => {
    const { container } = selectBoth()
    expect(container.textContent).toContain('2 selected')
  })

  it('Compare is enabled only at exactly two selections', () => {
    mockResponse = { data: { workspaces: [baseItem, secondItem], total: 2 }, isLoading: false }
    renderPanel()
    fireEvent.click(screen.getByLabelText('Select workspace e4-panel'))
    const compare = () =>
      screen
        .getAllByRole('button')
        .find((b) => (b.textContent ?? '') === 'Compare')! as HTMLButtonElement
    expect(compare().disabled).toBe(true)
    fireEvent.click(screen.getByLabelText('Select workspace second'))
    expect(compare().disabled).toBe(false)
    fireEvent.click(compare())
    expect(mockNavigate).toHaveBeenCalledWith(
      `/showcase/compare?a=${baseItem.workspace_id}&b=${secondItem.workspace_id}`,
    )
  })

  it('delete-selected confirms once then issues N sequential single deletes', async () => {
    mockDeleteResult.mutateAsync.mockResolvedValue(undefined)
    selectBoth()
    fireEvent.click(
      screen.getAllByRole('button').find((b) => (b.textContent ?? '').includes('Delete selected'))!,
    )
    // Nothing deleted before the confirmation.
    expect(mockDeleteResult.mutateAsync).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('Delete 2 workspace records?')
    fireEvent.click(screen.getByTestId('workspace-multi-delete-confirm'))
    await waitFor(() => expect(mockDeleteResult.mutateAsync).toHaveBeenCalledTimes(2))
    expect(mockDeleteResult.mutateAsync).toHaveBeenNthCalledWith(1, baseItem.workspace_id)
    expect(mockDeleteResult.mutateAsync).toHaveBeenNthCalledWith(2, secondItem.workspace_id)
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('2 workspace records')),
    )
  })

  it('collects multi-delete failures into one error toast', async () => {
    mockDeleteResult.mutateAsync
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new ApiError('Workspace not found', 404))
    selectBoth()
    fireEvent.click(
      screen.getAllByRole('button').find((b) => (b.textContent ?? '').includes('Delete selected'))!,
    )
    fireEvent.click(screen.getByTestId('workspace-multi-delete-confirm'))
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('Some deletes failed')),
    )
  })
})

describe('WorkspacePanel — single delete', () => {
  function openDeleteDialog() {
    mockResponse = { data: { workspaces: [baseItem], total: 1 }, isLoading: false }
    const result = renderPanel({ onDeleted: vi.fn() })
    radixOpen(screen.getByLabelText('More actions for e4-panel'))
    fireEvent.click(screen.getByText('Delete…'))
    return result
  }

  it('shows a confirmation whose copy makes metadata-only deletion clear', () => {
    openDeleteDialog()
    expect(mockDeleteResult.mutate).not.toHaveBeenCalled()
    const copy = document.body.textContent ?? ''
    expect(copy).toContain('Delete workspace "e4-panel"?')
    expect(copy).toContain('only the saved workspace record')
    expect(copy).toContain('NOT deleted')
  })

  it('confirming deletes the row and notifies the page on success', () => {
    const onDeleted = vi.fn()
    mockResponse = { data: { workspaces: [baseItem], total: 1 }, isLoading: false }
    renderPanel({ onDeleted })
    radixOpen(screen.getByLabelText('More actions for e4-panel'))
    fireEvent.click(screen.getByText('Delete…'))
    fireEvent.click(screen.getByTestId('workspace-delete-confirm'))

    expect(mockDeleteResult.mutate).toHaveBeenCalledTimes(1)
    const [workspaceId, options] = mockDeleteResult.mutate.mock.calls[0] as [
      string,
      { onSuccess: () => void; onError: (error: unknown) => void },
    ]
    expect(workspaceId).toBe(baseItem.workspace_id)
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
