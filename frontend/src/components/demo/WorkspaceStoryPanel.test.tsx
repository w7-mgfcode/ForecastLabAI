/**
 * E5 (#411) — render tests for WorkspaceStoryPanel: approval history,
 * knowledge events, reproduction markers, and the legacy self-hide path.
 */

import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { WorkspaceStoryPanel } from './WorkspaceStoryPanel'
import type { WorkspaceDetail } from '@/types/api'

afterEach(() => cleanup())

const baseWorkspace: WorkspaceDetail = {
  workspace_id: 'a'.repeat(32),
  name: 'e5-story',
  status: 'completed',
  seed: 42,
  scenario: 'showcase_rich',
  reset: false,
  skip_seed: true,
  result_summary: null,
  created_at: '2026-06-01T12:00:00Z',
  store_id: 3,
  product_id: 7,
  date_start: '2026-01-01',
  date_end: '2026-03-31',
  created_objects: {},
  archived: false,
  pinned: false,
  tags: [],
  replayed_from_workspace_id: null,
  seed_overrides: null,
  user_scope: null,
  run_config: null,
  notes: null,
  config_schema_version: 2,
  approval_events: null,
  rag_events: null,
}

function renderPanel(workspace: WorkspaceDetail) {
  return render(<WorkspaceStoryPanel workspace={workspace} />)
}

describe('WorkspaceStoryPanel', () => {
  it('renders nothing for a legacy row with no slots and no reproduction', () => {
    const { container } = renderPanel(baseWorkspace)
    expect(container.firstChild).toBeNull()
    expect(screen.queryByTestId('workspace-story-panel')).toBeNull()
  })

  it('renders approval history with a decision badge, tool, and transcript snippet', () => {
    const workspace: WorkspaceDetail = {
      ...baseWorkspace,
      approval_events: [
        {
          action_id: 'act-1',
          tool_name: 'save_scenario',
          decision: 'rejected',
          decided_at: '2026-06-01T12:05:00Z',
          session_id: 'sess-1',
          auto_approved: false,
          reason: 'not now',
          execution_status: 'rejected',
          transcript_summary: 'I would like to save this scenario plan.',
          tokens_used: 240,
          tool_calls_count: 1,
        },
      ],
    }
    const { container } = renderPanel(workspace)
    expect(screen.getByTestId('workspace-story-panel')).toBeTruthy()
    expect(container.textContent).toContain('rejected')
    expect(container.textContent).toContain('save_scenario')
    expect(container.textContent).toContain('I would like to save this scenario plan.')
    expect(container.textContent).toContain('reason: not now')
  })

  it('renders knowledge events with event/status/provider/count', () => {
    const workspace: WorkspaceDetail = {
      ...baseWorkspace,
      rag_events: [
        {
          event: 'index',
          status: 'pass',
          detail: 'indexed 5 files',
          count: 42,
          occurred_at: '2026-06-01T12:03:00Z',
          provider: 'openai',
          reachable: null,
        },
      ],
    }
    const { container } = renderPanel(workspace)
    expect(container.textContent).toContain('index')
    expect(container.textContent).toContain('pass')
    expect(container.textContent).toContain('openai')
    expect(container.textContent).toContain('count: 42')
  })

  it('renders reproduction markers only when story_reproduction is present', () => {
    const workspace: WorkspaceDetail = {
      ...baseWorkspace,
      result_summary: {
        story_reproduction: {
          agent: 'reproduced',
          knowledge: 'not_reproduced',
          source_workspace_id: 'b'.repeat(32),
        },
      },
    }
    renderPanel(workspace)
    const marker = screen.getByTestId('story-reproduction')
    expect(marker.textContent).toContain('agent')
    expect(marker.textContent).toContain('reproduced')
    expect(marker.textContent).toContain('knowledge')
    expect(marker.textContent).toContain('not reproduced')
    // source_workspace_id is not rendered as a verdict chip.
    expect(marker.textContent).not.toContain('source_workspace_id')
  })
})
