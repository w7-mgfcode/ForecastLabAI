import { describe, expect, it } from 'vitest'
import { buildReplayRequest } from './replay-request'
import type { WorkspaceListItem } from '@/types/api'

const baseItem: WorkspaceListItem = {
  workspace_id: 'a'.repeat(32),
  name: 'replayable',
  status: 'completed',
  seed: 7,
  scenario: 'showcase_rich',
  reset: true,
  skip_seed: false,
  result_summary: null,
  created_at: '2026-06-01T12:00:00Z',
  archived: false,
  pinned: false,
  tags: [],
  replayed_from_workspace_id: null,
}

describe('buildReplayRequest', () => {
  it('re-submits the recorded config verbatim with keep + provenance', () => {
    expect(buildReplayRequest(baseItem)).toEqual({
      seed: 7,
      scenario: 'showcase_rich',
      reset: true,
      skip_seed: false,
      preservation: 'keep',
      replayed_from_workspace_id: baseItem.workspace_id,
      workspace_name: 'replayable',
    })
  })

  it('omits workspace_name on an unnamed row (names stay optional)', () => {
    const request = buildReplayRequest({ ...baseItem, name: null })
    expect('workspace_name' in request).toBe(false)
    expect(request.preservation).toBe('keep')
  })
})
