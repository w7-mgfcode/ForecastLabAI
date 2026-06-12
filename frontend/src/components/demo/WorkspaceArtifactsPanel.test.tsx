import { cleanup, render } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { WorkspaceArtifactsPanel } from './WorkspaceArtifactsPanel'
import type { WorkspaceDetail } from '@/types/api'

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
}

function renderPanel(workspace: WorkspaceDetail) {
  return render(
    <MemoryRouter>
      <WorkspaceArtifactsPanel workspace={workspace} />
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
