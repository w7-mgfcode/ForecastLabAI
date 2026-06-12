import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { WorkspaceArtifactsPanel } from './WorkspaceArtifactsPanel'
import type { WorkspaceDetail, WorkspaceHealth } from '@/types/api'

afterEach(() => cleanup())

const fullWorkspace: WorkspaceDetail = {
  workspace_id: 'a'.repeat(32),
  name: 'e4-artifacts',
  status: 'completed',
  seed: 42,
  scenario: 'showcase_rich',
  reset: false,
  skip_seed: true,
  result_summary: { winner_model_type: 'prophet_like' },
  created_at: '2026-06-01T12:00:00Z',
  store_id: 3,
  product_id: 7,
  date_start: '2026-01-01',
  date_end: '2026-03-31',
  created_objects: {
    winning_run_id: 'run-win',
    v2_run_id: 'run-v2',
    batch_id: 'batch-1',
    alias: 'demo-production',
    agent_session_id: 'sess-1',
    scenario_plan_ids: ['sp-1', 'sp-2'],
  },
  archived: false,
  pinned: false,
  tags: [],
  replayed_from_workspace_id: null,
  notes: null,
  config_schema_version: 1,
}

function renderPanel(workspace: WorkspaceDetail, health: WorkspaceHealth | null = null) {
  return render(
    <MemoryRouter>
      <WorkspaceArtifactsPanel workspace={workspace} health={health} />
    </MemoryRouter>,
  )
}

describe('WorkspaceArtifactsPanel', () => {
  it('renders deep links for every recorded object', () => {
    const { container } = renderPanel(fullWorkspace)
    const hrefs = Array.from(container.querySelectorAll('a')).map((a) =>
      a.getAttribute('href'),
    )
    expect(hrefs).toContain('/explorer/runs/run-win')
    expect(hrefs).toContain('/explorer/runs/run-v2')
    expect(hrefs).toContain('/visualize/planner?scenario_id=sp-1')
    expect(hrefs).toContain('/visualize/planner?scenario_id=sp-2')
    expect(hrefs).toContain('/visualize/batch/batch-1')
    expect(hrefs).toContain('/ops')
    expect(hrefs).toContain('/visualize/forecast?store_id=3&product_id=7')
    expect(hrefs).toContain('/visualize/backtest?store_id=3&product_id=7')
    expect(hrefs).toContain('/chat')
    expect(container.textContent).toContain('e4-artifacts')
  })

  it('renders disabled cards (no links) when objects are missing', () => {
    const empty: WorkspaceDetail = {
      ...fullWorkspace,
      name: null,
      store_id: null,
      product_id: null,
      created_objects: {},
    }
    const { container } = renderPanel(empty)
    // Nothing recorded -> no active links at all.
    expect(container.querySelectorAll('a').length).toBe(0)
    // Disabled cards still render their labels (with the id-slice header).
    expect(container.textContent).toContain('Winning run')
    expect(container.textContent).toContain('Scenario plans')
    expect(container.textContent).toContain('aaaaaaaa')
  })

  it('tolerates malformed created_objects values', () => {
    const malformed: WorkspaceDetail = {
      ...fullWorkspace,
      created_objects: {
        winning_run_id: 123, // wrong type -> treated as missing
        scenario_plan_ids: 'not-a-list',
      },
    }
    const { container } = renderPanel(malformed)
    const hrefs = Array.from(container.querySelectorAll('a')).map((a) =>
      a.getAttribute('href'),
    )
    expect(hrefs).not.toContain('/explorer/runs/123')
    // Grain links still resolve from the columns.
    expect(hrefs).toContain('/visualize/forecast?store_id=3&product_id=7')
  })
})

// =============================================================================
// E2 (#408) — link-health markers + summary chip
// =============================================================================

const baseHealth: WorkspaceHealth = {
  workspace_id: fullWorkspace.workspace_id,
  workspace_status: 'completed',
  partial_run: false,
  references: [],
  alive: 0,
  dead: 0,
  unknown: 0,
  checked_at: '2026-06-13T00:00:00Z',
}

describe('WorkspaceArtifactsPanel — health', () => {
  it('renders the summary chip with alive/dead counts', () => {
    const health: WorkspaceHealth = { ...baseHealth, alive: 5, dead: 2 }
    renderPanel(fullWorkspace, health)
    const chip = screen.getByTestId('workspace-health-summary')
    expect(chip.textContent).toContain('5 live')
    expect(chip.textContent).toContain('2 dead')
  })

  it('hides the dead count at zero and the chip without health data', () => {
    const { container, unmount } = renderPanel(fullWorkspace, { ...baseHealth, alive: 3 })
    expect(container.textContent).toContain('3 live')
    expect(container.textContent).not.toContain('dead')
    unmount()
    renderPanel(fullWorkspace, null)
    expect(screen.queryByTestId('workspace-health-summary')).toBeNull()
  })

  it('marks a card whose reference probed dead — unknown gets no marker', () => {
    const health: WorkspaceHealth = {
      ...baseHealth,
      alive: 4,
      dead: 1,
      unknown: 1,
      references: [
        {
          key: 'scenario_plan_ids[0]',
          ref_type: 'scenario_plan',
          ref_id: 'sp-1',
          status: 'dead',
          probe_path: '/scenarios/sp-1',
        },
        {
          key: 'batch_id',
          ref_type: 'batch',
          ref_id: 'batch-1',
          status: 'unknown',
          probe_path: '/batch/batch-1',
        },
      ],
    }
    renderPanel(fullWorkspace, health)
    expect(screen.getByTestId('dead-link-sp-1')).toBeTruthy()
    expect(screen.queryByTestId('dead-link-batch-1')).toBeNull()
  })

  it('renders the partial-run badge for a never-completed row', () => {
    const health: WorkspaceHealth = {
      ...baseHealth,
      workspace_status: 'failed',
      partial_run: true,
    }
    const { container } = renderPanel({ ...fullWorkspace, status: 'failed' }, health)
    expect(container.textContent).toContain('partial run')
  })
})
