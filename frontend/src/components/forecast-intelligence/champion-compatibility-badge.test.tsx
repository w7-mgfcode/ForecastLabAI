import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { ChampionCompatibilityBadge } from './champion-compatibility-badge'
import { computeCompatibility } from './champion-compatibility-utils'
import type { ModelRun } from '@/types/api'

afterEach(cleanup)

function makeRun(overrides: Partial<ModelRun>): ModelRun {
  return {
    run_id: overrides.run_id ?? 'r',
    status: 'success',
    model_type: 'naive',
    model_family: 'baseline',
    model_config: {},
    feature_config: null,
    config_hash: 'h',
    data_window_start: '2024-01-01',
    data_window_end: '2024-06-30',
    store_id: 1,
    product_id: 1,
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
    created_at: '2024-01-01',
    updated_at: '2024-01-01',
    ...overrides,
  }
}

describe('computeCompatibility', () => {
  it('returns ok=true when grain matches, windows overlap, V matches', () => {
    const a = makeRun({ run_id: 'a' })
    const b = makeRun({
      run_id: 'b',
      data_window_start: '2024-03-01',
      data_window_end: '2024-08-31',
    })
    expect(computeCompatibility(a, b)).toEqual({ ok: true })
  })

  it('rejects different store_id', () => {
    const a = makeRun({ store_id: 1 })
    const b = makeRun({ store_id: 2 })
    expect(computeCompatibility(a, b).ok).toBe(false)
    expect(computeCompatibility(a, b).reason).toMatch(/grain/i)
  })

  it('rejects different product_id', () => {
    const a = makeRun({ product_id: 1 })
    const b = makeRun({ product_id: 2 })
    expect(computeCompatibility(a, b).reason).toMatch(/grain/i)
  })

  it('rejects non-overlapping windows', () => {
    const a = makeRun({
      data_window_start: '2024-01-01',
      data_window_end: '2024-02-01',
    })
    const b = makeRun({
      data_window_start: '2024-06-01',
      data_window_end: '2024-09-01',
    })
    expect(computeCompatibility(a, b).reason).toMatch(/no data-window overlap/i)
  })

  it('rejects different feature_frame_version (V1 vs V2)', () => {
    const a = makeRun({ feature_frame_version: 1 })
    const b = makeRun({ feature_frame_version: 2 })
    expect(computeCompatibility(a, b).reason).toMatch(/feature frame version/i)
  })

  it('treats undefined feature_frame_version as V1', () => {
    const a = makeRun({})
    const b = makeRun({ feature_frame_version: 1 })
    expect(computeCompatibility(a, b)).toEqual({ ok: true })
  })

  it('treats null feature_frame_version as V1', () => {
    const a = makeRun({ feature_frame_version: null })
    const b = makeRun({})
    expect(computeCompatibility(a, b)).toEqual({ ok: true })
  })

  it('rejects unparseable dates', () => {
    const a = makeRun({ data_window_start: 'garbage' })
    const b = makeRun({})
    expect(computeCompatibility(a, b).reason).toMatch(/unparseable/i)
  })
})

describe('ChampionCompatibilityBadge', () => {
  it('renders the comparable label for a matching pair', () => {
    const a = makeRun({})
    const b = makeRun({})
    render(<ChampionCompatibilityBadge runA={a} runB={b} />)
    const badge = screen.getByTestId('champion-compatibility-badge')
    expect(badge.getAttribute('data-comparable')).toBe('yes')
    expect(badge.textContent).toBe('Comparable')
  })

  it('renders the not-comparable label when V differs', () => {
    const a = makeRun({ feature_frame_version: 1 })
    const b = makeRun({ feature_frame_version: 2 })
    render(<ChampionCompatibilityBadge runA={a} runB={b} />)
    const badge = screen.getByTestId('champion-compatibility-badge')
    expect(badge.getAttribute('data-comparable')).toBe('no')
    expect(badge.textContent).toBe('Not comparable')
  })
})
