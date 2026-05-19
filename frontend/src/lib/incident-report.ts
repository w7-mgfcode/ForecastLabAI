// Builders for the ForecastOps incident report — a client-side CSV + Markdown
// export of the operational snapshot already loaded on the /ops page. The
// builders take no I/O and are unit-tested (incident-report.test.ts);
// downloadMarkdown is the one DOM-touching helper (mirrors csv-export.ts).
import type { CsvColumn } from '@/lib/csv-export'
import { formatWapeDelta } from '@/lib/ops-utils'
import type {
  AttentionItem,
  ModelHealthEntry,
  OpsSummaryResponse,
  RetrainingCandidate,
} from '@/types/api'

/** CSV column set for the attention-items export (feed to toCsv / downloadCsv). */
export const attentionCsvColumns: CsvColumn<AttentionItem>[] = [
  { key: 'item_type', header: 'Type' },
  { key: 'entity_id', header: 'Entity' },
  { key: 'label', header: 'Item' },
  { key: 'detail', header: 'Detail' },
  { key: 'occurred_at', header: 'When' },
]

/** Render a value for a Markdown table cell: '—' for empty, pipes/newlines neutralised. */
function mdCell(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
    .replace(/\|/g, '\\|')
    .replace(/[\r\n]+/g, ' ')
}

/** Percentage display for the run success rate; '—' when null. */
function pct(rate: number | null): string {
  return rate === null ? '—' : `${(rate * 100).toFixed(1)}%`
}

/** One-decimal WAPE display; '—' when null. */
function wape(value: number | null): string {
  return value === null ? '—' : value.toFixed(1)
}

/**
 * Build a human-readable Markdown incident report from already-loaded /ops
 * page data. Pure: no fetch, no DOM, deterministic for a given input — the
 * timestamps are emitted verbatim so the output is stable for unit tests.
 */
export function buildIncidentMarkdown(
  summary: OpsSummaryResponse,
  candidates: RetrainingCandidate[],
  modelHealth: ModelHealthEntry[],
): string {
  const staleAliases = summary.aliases.filter((alias) => alias.is_stale).length
  const lines: string[] = [
    '# ForecastOps Incident Report',
    '',
    `_Generated ${summary.generated_at}_`,
    '',
    '## System Health',
    '',
    `- API: ${summary.system.api_ok ? 'ok' : 'down'}`,
    `- Database: ${summary.system.database_connected ? 'connected' : 'down'}`,
    `- Latest successful job: ${summary.system.latest_successful_job_at ?? '—'}`,
    '',
    '## KPIs',
    '',
    `- Active jobs: ${summary.jobs.active_total}`,
    `- Failed jobs: ${summary.jobs.failed_total}`,
    `- Completed today: ${summary.jobs.completed_today}`,
    `- Run success rate: ${pct(summary.runs.success_rate)}`,
    `- Failed runs: ${summary.runs.failed_total}`,
    `- Stale aliases: ${staleAliases} of ${summary.aliases.length}`,
    '',
    '## Data Freshness',
    '',
    `- Latest sales date: ${summary.freshness.latest_sales_date ?? '—'}`,
    `- Latest completed job: ${summary.freshness.latest_job_completed_at ?? '—'}`,
    `- Latest successful run: ${summary.freshness.latest_run_completed_at ?? '—'}`,
    '',
    `## Needs Attention (${summary.attention_items.length})`,
    '',
  ]

  if (summary.attention_items.length === 0) {
    lines.push('_Nothing needs attention._', '')
  } else {
    lines.push('| Type | Item | Detail | When |', '| --- | --- | --- | --- |')
    for (const item of summary.attention_items) {
      lines.push(
        `| ${mdCell(item.item_type)} | ${mdCell(item.label)} | ${mdCell(item.detail)} | ${mdCell(item.occurred_at)} |`,
      )
    }
    lines.push('')
  }

  lines.push(`## Model Health — Drift (${modelHealth.length})`, '')
  if (modelHealth.length === 0) {
    lines.push('_No model health to evaluate._', '')
  } else {
    lines.push(
      '| Store | Product | Drift | Latest WAPE | Δ WAPE | Runs |',
      '| --- | --- | --- | --- | --- | --- |',
    )
    for (const entry of modelHealth) {
      lines.push(
        `| ${mdCell(entry.store_id)} | ${mdCell(entry.product_id)} | ${mdCell(entry.drift_direction)} | ${wape(entry.latest_wape)} | ${formatWapeDelta(entry.wape_delta)} | ${mdCell(entry.run_count)} |`,
      )
    }
    lines.push('')
  }

  lines.push(`## Top Retraining Candidates (${candidates.length})`, '')
  if (candidates.length === 0) {
    lines.push('_No retraining candidates._', '')
  } else {
    lines.push(
      '| Store | Product | Priority | Staleness (days) | WAPE | Reason |',
      '| --- | --- | --- | --- | --- | --- |',
    )
    for (const candidate of candidates) {
      lines.push(
        `| ${mdCell(candidate.store_id)} | ${mdCell(candidate.product_id)} | ${candidate.priority_score.toFixed(2)} | ${mdCell(candidate.staleness_days)} | ${wape(candidate.wape)} | ${mdCell(candidate.reason)} |`,
      )
    }
    lines.push('')
  }

  return lines.join('\n')
}

/** Trigger a browser download of `content` as a Markdown file. */
export function downloadMarkdown(filename: string, content: string): void {
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
