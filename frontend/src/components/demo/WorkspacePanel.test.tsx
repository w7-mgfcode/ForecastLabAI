import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { WorkspacePanel } from './WorkspacePanel'
import type { WorkspaceListItem, WorkspaceListResponse } from '@/types/api'

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

vi.mock('@/hooks/use-workspaces', () => ({
  useWorkspaces: () => mockResponse,
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
