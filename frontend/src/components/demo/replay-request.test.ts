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
  seed_overrides: null,
  user_scope: null,
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

  // E3 (#409) — replay-verbatim covers the recorded story slots.
  it('omits the E3 keys on a legacy row (null slots) — byte-identical frame', () => {
    const request = buildReplayRequest(baseItem)
    expect('seed_overrides' in request).toBe(false)
    expect('user_scope' in request).toBe(false)
  })

  it('re-submits recorded seed_overrides and user_scope verbatim', () => {
    const slotted: WorkspaceListItem = {
      ...baseItem,
      seed_overrides: { stores: 8, products: 20, promotion_intensity: 0.3 },
      user_scope: { store_id: 12, product_id: 47 },
    }
    const request = buildReplayRequest(slotted)
    expect(request.seed_overrides).toEqual({
      stores: 8,
      products: 20,
      promotion_intensity: 0.3,
    })
    expect(request.user_scope).toEqual({ store_id: 12, product_id: 47 })
    // Lineage stays intact when the slots ride along (E1 frozen criterion).
    expect(request.replayed_from_workspace_id).toBe(baseItem.workspace_id)
  })
})
