import { describe, it, expect } from 'vitest'
import {
  attentionBadgeVariant,
  attentionItemLink,
  formatStaleness,
  sortRetrainingCandidates,
  summaryHealthVariant,
} from './ops-utils'
import type { AttentionItem, RetrainingCandidate, SystemHealth } from '@/types/api'

/** Build an AttentionItem with sensible defaults for fields not under test. */
function makeItem(partial: Partial<AttentionItem> & Pick<AttentionItem, 'item_type'>): AttentionItem {
  return {
    item_type: partial.item_type,
    entity_id: partial.entity_id ?? 'entity-1',
    label: partial.label ?? 'label',
    detail: partial.detail ?? 'detail',
    occurred_at: partial.occurred_at ?? null,
  }
}

/** Build a RetrainingCandidate with sensible defaults. */
function makeCandidate(
  partial: Partial<RetrainingCandidate> & Pick<RetrainingCandidate, 'priority_score'>,
): RetrainingCandidate {
  return {
    store_id: partial.store_id ?? 1,
    product_id: partial.product_id ?? 1,
    priority_score: partial.priority_score,
    staleness_days: partial.staleness_days ?? 0,
    wape: partial.wape ?? null,
    latest_run_id: partial.latest_run_id ?? 'run-1',
    latest_run_status: partial.latest_run_status ?? 'success',
    reason: partial.reason ?? 'reason',
  }
}

describe('summaryHealthVariant', () => {
  it('is success when API and database are both up', () => {
    const system: SystemHealth = {
      api_ok: true,
      database_connected: true,
      latest_successful_job_at: null,
    }
    expect(summaryHealthVariant(system)).toBe('success')
  })

  it('is error when the database is down', () => {
    const system: SystemHealth = {
      api_ok: true,
      database_connected: false,
      latest_successful_job_at: null,
    }
    expect(summaryHealthVariant(system)).toBe('error')
  })
})

describe('attentionItemLink', () => {
  it('links a failed job to the job detail page', () => {
    expect(attentionItemLink(makeItem({ item_type: 'failed_job', entity_id: 'job-9' }))).toBe(
      '/explorer/jobs/job-9',
    )
  })

  it('links a failed run to the run detail page', () => {
    expect(attentionItemLink(makeItem({ item_type: 'failed_run', entity_id: 'run-9' }))).toBe(
      '/explorer/runs/run-9',
    )
  })

  it('links a stale alias to the run detail page', () => {
    expect(attentionItemLink(makeItem({ item_type: 'stale_alias', entity_id: 'run-3' }))).toBe(
      '/explorer/runs/run-3',
    )
  })
})

describe('attentionBadgeVariant', () => {
  it('warns for a stale alias', () => {
    expect(attentionBadgeVariant('stale_alias')).toBe('warning')
  })

  it('errors for failed jobs and runs', () => {
    expect(attentionBadgeVariant('failed_job')).toBe('error')
    expect(attentionBadgeVariant('failed_run')).toBe('error')
  })
})

describe('formatStaleness', () => {
  it('renders a positive day count', () => {
    expect(formatStaleness(12)).toBe('12d')
  })

  it('renders "today" at zero or negative days', () => {
    expect(formatStaleness(0)).toBe('today')
    expect(formatStaleness(-3)).toBe('today')
  })
})

describe('sortRetrainingCandidates', () => {
  it('sorts by priority score descending', () => {
    const sorted = sortRetrainingCandidates([
      makeCandidate({ priority_score: 0.2 }),
      makeCandidate({ priority_score: 0.9 }),
      makeCandidate({ priority_score: 0.5 }),
    ])
    expect(sorted.map((c) => c.priority_score)).toEqual([0.9, 0.5, 0.2])
  })

  it('does not mutate the input array', () => {
    const input = [makeCandidate({ priority_score: 0.1 }), makeCandidate({ priority_score: 0.8 })]
    sortRetrainingCandidates(input)
    expect(input.map((c) => c.priority_score)).toEqual([0.1, 0.8])
  })

  it('returns an empty array unchanged', () => {
    expect(sortRetrainingCandidates([])).toEqual([])
  })
})
