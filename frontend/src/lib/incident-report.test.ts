import { describe, it, expect } from 'vitest'
import { attentionCsvColumns, buildIncidentMarkdown } from './incident-report'
import type {
  AttentionItem,
  ModelHealthEntry,
  OpsSummaryResponse,
  RetrainingCandidate,
} from '@/types/api'

/** Build an OpsSummaryResponse with sensible defaults for fields not under test. */
function makeSummary(overrides: Partial<OpsSummaryResponse> = {}): OpsSummaryResponse {
  return {
    system: {
      api_ok: true,
      database_connected: true,
      latest_successful_job_at: '2026-05-19T10:00:00Z',
    },
    jobs: { counts: [], completed_today: 2, failed_total: 1, active_total: 3 },
    runs: { counts: [], success_rate: 0.8, failed_total: 1 },
    aliases: [],
    freshness: {
      latest_sales_date: '2026-05-18',
      latest_job_completed_at: '2026-05-19T09:00:00Z',
      latest_run_completed_at: '2026-05-19T08:00:00Z',
    },
    attention_items: [],
    generated_at: '2026-05-19T12:00:00Z',
    ...overrides,
  }
}

/** Build an AttentionItem with sensible defaults. */
function makeAttentionItem(
  partial: Partial<AttentionItem> & Pick<AttentionItem, 'item_type'>,
): AttentionItem {
  return {
    item_type: partial.item_type,
    entity_id: partial.entity_id ?? 'e1',
    label: partial.label ?? 'label',
    detail: partial.detail ?? 'detail',
    occurred_at: partial.occurred_at ?? null,
  }
}

/** Build a ModelHealthEntry with sensible defaults. */
function makeHealthEntry(partial: Partial<ModelHealthEntry> = {}): ModelHealthEntry {
  return {
    store_id: partial.store_id ?? 1,
    product_id: partial.product_id ?? 2,
    run_count: partial.run_count ?? 3,
    latest_run_id: partial.latest_run_id ?? 'r1',
    latest_run_status: partial.latest_run_status ?? 'success',
    latest_wape: partial.latest_wape ?? 25,
    previous_wape: partial.previous_wape ?? 11,
    wape_delta: partial.wape_delta ?? 14,
    drift_direction: partial.drift_direction ?? 'degrading',
    last_trained_at: partial.last_trained_at ?? null,
    staleness_days: partial.staleness_days ?? 10,
    wape_history: partial.wape_history ?? [],
  }
}

/** Build a RetrainingCandidate with sensible defaults. */
function makeCandidate(partial: Partial<RetrainingCandidate> = {}): RetrainingCandidate {
  return {
    store_id: partial.store_id ?? 1,
    product_id: partial.product_id ?? 2,
    priority_score: partial.priority_score ?? 0.75,
    staleness_days: partial.staleness_days ?? 30,
    wape: partial.wape ?? 12,
    latest_run_id: partial.latest_run_id ?? 'r1',
    latest_run_status: partial.latest_run_status ?? 'success',
    reason: partial.reason ?? 'reason',
  }
}

describe('attentionCsvColumns', () => {
  it('exposes the five attention-item columns in order', () => {
    expect(attentionCsvColumns.map((column) => column.key)).toEqual([
      'item_type',
      'entity_id',
      'label',
      'detail',
      'occurred_at',
    ])
  })
})

describe('buildIncidentMarkdown', () => {
  it('renders the report title and generated timestamp', () => {
    const md = buildIncidentMarkdown(makeSummary(), [], [])
    expect(md).toContain('# ForecastOps Incident Report')
    expect(md).toContain('_Generated 2026-05-19T12:00:00Z_')
  })

  it('renders KPI lines from the summary', () => {
    const md = buildIncidentMarkdown(makeSummary(), [], [])
    expect(md).toContain('- Active jobs: 3')
    expect(md).toContain('- Run success rate: 80.0%')
  })

  it('shows the empty-state line when nothing needs attention', () => {
    const md = buildIncidentMarkdown(makeSummary(), [], [])
    expect(md).toContain('## Needs Attention (0)')
    expect(md).toContain('_Nothing needs attention._')
  })

  it('renders an attention table row and escapes pipe characters', () => {
    const summary = makeSummary({
      attention_items: [
        makeAttentionItem({ item_type: 'failed_job', label: 'train', detail: 'a | b' }),
      ],
    })
    const md = buildIncidentMarkdown(summary, [], [])
    expect(md).toContain('## Needs Attention (1)')
    expect(md).toContain('a \\| b')
  })

  it('renders the model-health drift section with a signed delta', () => {
    const md = buildIncidentMarkdown(makeSummary(), [], [
      makeHealthEntry({ drift_direction: 'degrading', wape_delta: 14 }),
    ])
    expect(md).toContain('## Model Health — Drift (1)')
    expect(md).toContain('degrading')
    expect(md).toContain('+14.0')
  })

  it('renders the retraining-candidates section', () => {
    const md = buildIncidentMarkdown(makeSummary(), [makeCandidate({ priority_score: 0.91 })], [])
    expect(md).toContain('## Top Retraining Candidates (1)')
    expect(md).toContain('0.91')
  })

  it('handles a null success rate', () => {
    const summary = makeSummary({ runs: { counts: [], success_rate: null, failed_total: 0 } })
    expect(buildIncidentMarkdown(summary, [], [])).toContain('- Run success rate: —')
  })
})
