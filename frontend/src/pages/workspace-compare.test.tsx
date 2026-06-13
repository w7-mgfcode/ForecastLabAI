import { cleanup, render } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import WorkspaceComparePage from './workspace-compare'
import type { WorkspaceDetail } from '@/types/api'

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

const idA = 'a'.repeat(32)
const idB = 'b'.repeat(32)

function makeDetail(overrides: Partial<WorkspaceDetail>): WorkspaceDetail {
  return {
    workspace_id: idA,
    name: 'ws-a',
    status: 'completed',
    seed: 42,
    scenario: 'demo_minimal',
    reset: false,
    skip_seed: true,
    result_summary: {
      winner_model_type: 'seasonal_naive',
      winner_wape: 0.15,
      wall_clock_s: 12,
    },
    created_at: '2026-06-01T12:00:00Z',
    archived: false,
    pinned: false,
    tags: [],
    replayed_from_workspace_id: null,
    seed_overrides: null,
    user_scope: null,
    store_id: 3,
    product_id: 7,
    date_start: '2026-01-01',
    date_end: '2026-03-31',
    created_objects: { winning_run_id: 'run-1', alias: 'demo-production' },
    notes: null,
    config_schema_version: 1,
    ...overrides,
  }
}

let details: Record<string, WorkspaceDetail | undefined> = {}

vi.mock('@/hooks/use-workspaces', () => ({
  useWorkspaces: () => ({
    data: {
      workspaces: Object.values(details).filter(Boolean),
      total: Object.keys(details).length,
    },
    isLoading: false,
  }),
  useWorkspace: (workspaceId: string, enabled = true) => {
    if (!enabled || !workspaceId) return { data: undefined, isLoading: false, error: null }
    const detail = details[workspaceId]
    return detail
      ? { data: detail, isLoading: false, error: null }
      : { data: undefined, isLoading: false, error: new Error('not found') }
  },
}))

beforeEach(() => {
  details = {
    [idA]: makeDetail({}),
    [idB]: makeDetail({
      workspace_id: idB,
      name: 'ws-b',
      seed: 99,
      status: 'failed',
      replayed_from_workspace_id: idA,
      result_summary: {
        winner_model_type: 'naive',
        winner_wape: 0.25,
        wall_clock_s: 20,
      },
      created_objects: { winning_run_id: 'run-2', batch_id: 'batch-1' },
    }),
  }
})

function renderPage(query = `?a=${idA}&b=${idB}`) {
  return render(
    <MemoryRouter initialEntries={[`/showcase/compare${query}`]}>
      <Routes>
        <Route path="/showcase/compare" element={<WorkspaceComparePage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('WorkspaceComparePage', () => {
  it('renders the config diff for two deep-linked workspaces', () => {
    const { container } = renderPage()
    const copy = container.textContent ?? ''
    expect(copy).toContain('ws-a')
    expect(copy).toContain('ws-b')
    expect(copy).toContain('42')
    expect(copy).toContain('99')
    // Mismatching seed rows are emphasized.
    const bolded = Array.from(container.querySelectorAll('td.font-semibold')).map(
      (el) => el.textContent,
    )
    expect(bolded).toContain('42')
    expect(bolded).toContain('99')
  })

  it('renders the result diff with the sign-only WAPE delta', () => {
    const { container } = renderPage()
    const copy = container.textContent ?? ''
    expect(copy).toContain('seasonal_naive')
    expect(copy).toContain('0.1500')
    expect(copy).toContain('0.2500')
    expect(copy).toContain('0.1000') // 0.25 - 0.15
  })

  it('renders the created-objects presence matrix over the key union', () => {
    const { container } = renderPage()
    const copy = container.textContent ?? ''
    expect(copy).toContain('winning_run_id')
    expect(copy).toContain('alias')
    expect(copy).toContain('batch_id')
  })

  it('renders the lineage note when one side replays the other', () => {
    const { container } = renderPage()
    expect(container.textContent).toContain('Workspace B is a replay of workspace A.')
  })

  it('renders the partial-run badge on a failed side', () => {
    const { container } = renderPage()
    expect(container.textContent).toContain('partial run')
  })

  it('degrades to the picker when an id no longer resolves (no crash)', () => {
    details[idB] = undefined
    const { container } = renderPage()
    expect(container.textContent).toContain('no longer exists')
    // The diff sections never render half-ready.
    expect(container.textContent).not.toContain('Created objects')
  })

  it('prompts for selection when ids are missing', () => {
    const { container } = renderPage('')
    expect(container.textContent).toContain('Select two workspaces')
  })
})
