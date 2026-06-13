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
  run_config: null,
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

  // E4 (#410) — replay-verbatim covers the recorded run config.
  it('omits run-config keys on a default-config row (null run_config)', () => {
    const request = buildReplayRequest(baseItem)
    expect('train_model_types' in request).toBe(false)
    expect('backtest' in request).toBe(false)
  })

  it('re-submits recorded run_config (model set + backtest) verbatim', () => {
    const configured: WorkspaceListItem = {
      ...baseItem,
      run_config: {
        train_model_types: ['naive', 'seasonal_average'],
        backtest: { horizon: 21, n_splits: 4, metric: 'rmse' },
      },
    }
    const request = buildReplayRequest(configured)
    expect(request.train_model_types).toEqual(['naive', 'seasonal_average'])
    expect(request.backtest?.horizon).toBe(21)
    expect(request.backtest?.n_splits).toBe(4)
    expect(request.backtest?.metric).toBe('rmse')
    // Missing knobs are filled from the defaults (verbatim-complete frame).
    expect(request.backtest?.strategy).toBe('expanding')
    expect(request.backtest?.min_train_size).toBe(30)
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
