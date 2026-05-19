import { describe, it, expect } from 'vitest'
import { buildRetrainJob } from './ops-actions'
import type { ModelRun } from '@/types/api'

/** Build a ModelRun with sensible defaults for fields not under test. */
function makeRun(overrides: Partial<ModelRun> = {}): ModelRun {
  return {
    run_id: 'r1',
    status: 'success',
    model_type: 'naive',
    model_config: { model_type: 'naive', schema_version: '1.0' },
    feature_config: null,
    config_hash: 'abc',
    data_window_start: '2025-01-01',
    data_window_end: '2026-01-01',
    store_id: 9,
    product_id: 8,
    metrics: null,
    artifact_uri: null,
    artifact_hash: null,
    artifact_size_bytes: null,
    runtime_info: null,
    agent_context: null,
    git_sha: null,
    error_message: null,
    started_at: null,
    completed_at: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('buildRetrainJob', () => {
  it('builds a train job with the flat param contract', () => {
    const job = buildRetrainJob(makeRun(), '2026-05-18')
    expect(job.job_type).toBe('train')
    expect(job.params).toEqual({
      model_type: 'naive',
      store_id: 9,
      product_id: 8,
      start_date: '2025-01-01',
      end_date: '2026-05-18',
    })
  })

  it('falls back to the run window end when no latest sales date is known', () => {
    expect(buildRetrainJob(makeRun(), null).params.end_date).toBe('2026-01-01')
  })

  it('lifts season_length for a seasonal_naive run', () => {
    const run = makeRun({
      model_type: 'seasonal_naive',
      model_config: { model_type: 'seasonal_naive', schema_version: '1.0', season_length: 7 },
    })
    expect(buildRetrainJob(run, null).params.season_length).toBe(7)
  })

  it('lifts window_size for a moving_average run', () => {
    const run = makeRun({
      model_type: 'moving_average',
      model_config: { model_type: 'moving_average', schema_version: '1.0', window_size: 14 },
    })
    expect(buildRetrainJob(run, null).params.window_size).toBe(14)
  })

  it('omits model-specific keys when model_config carries none', () => {
    const job = buildRetrainJob(makeRun(), null)
    expect(job.params).not.toHaveProperty('season_length')
    expect(job.params).not.toHaveProperty('window_size')
  })

  it('ignores non-numeric model_config values', () => {
    const run = makeRun({
      model_config: { model_type: 'seasonal_naive', season_length: 'weekly' },
    })
    expect(buildRetrainJob(run, null).params).not.toHaveProperty('season_length')
  })
})
