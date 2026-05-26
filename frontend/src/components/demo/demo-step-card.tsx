import { ArrowUpRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { DemoStep, DemoStepUiStatus } from '@/hooks/use-demo-pipeline'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { HorizonBucketsMini } from './HorizonBucketsMini'

// Status glyphs -- the vocabulary from .claude/rules/output-formatting.md.
const STATUS_GLYPH: Record<DemoStepUiStatus, string> = {
  idle: '○',
  running: '🔄',
  pass: '✅',
  fail: '❌',
  skip: '⏭️',
  warn: '⚠️',
}

// Left-border accent colour per status.
const STATUS_ACCENT: Record<DemoStepUiStatus, string> = {
  idle: 'border-l-border',
  running: 'border-l-info',
  pass: 'border-l-success',
  fail: 'border-l-destructive',
  skip: 'border-l-muted-foreground/40',
  warn: 'border-l-warning',
}

function formatDuration(ms: number): string {
  if (ms <= 0) return ''
  if (ms < 1000) return `${Math.round(ms)} ms`
  return `${(ms / 1000).toFixed(1)} s`
}

/** Per-model WAPE breakdown rendered inside the backtest step card. */
function BacktestBreakdown({ data }: { data: Record<string, unknown> }) {
  const perModel = data.per_model
  const winner = typeof data.winner === 'string' ? data.winner : null
  if (perModel === null || typeof perModel !== 'object') return null

  const rows = Object.entries(perModel as Record<string, unknown>).map(([model, metrics]) => {
    const wape =
      metrics !== null && typeof metrics === 'object'
        ? (metrics as Record<string, unknown>).wape
        : undefined
    return { model, wape: typeof wape === 'number' ? wape : null }
  })

  return (
    <div className="mt-3 space-y-1">
      {rows.map((row) => (
        <div
          key={row.model}
          className={cn(
            'flex items-center justify-between rounded-md px-2 py-1 text-xs',
            row.model === winner
              ? 'bg-success/10 font-semibold'
              : 'bg-muted'
          )}
        >
          <span className="font-mono">
            {row.model === winner ? '🏆 ' : ''}
            {row.model}
          </span>
          <span className="font-mono">
            WAPE {row.wape !== null ? row.wape.toFixed(4) : 'n/a'}
          </span>
        </div>
      ))}
    </div>
  )
}

/** Registered-run detail rendered inside the register step card. */
function RegisterDetail({ data }: { data: Record<string, unknown> }) {
  const runId = typeof data.run_id === 'string' ? data.run_id : null
  const alias = typeof data.alias === 'string' ? data.alias : null
  if (!runId) return null
  return (
    <div className="mt-3 flex flex-wrap gap-2 text-xs">
      <span className="rounded-md bg-muted px-2 py-1 font-mono">run_id: {runId}</span>
      {alias && (
        <span className="rounded-md bg-muted px-2 py-1 font-mono">alias: {alias}</span>
      )}
    </div>
  )
}

/** PRP-39 — champion-compat compare mini-summary chip-line. */
function ChampionCompatDetail({ data }: { data: Record<string, unknown> }) {
  const va = data.feature_frame_version_a
  const vb = data.feature_frame_version_b
  const compatible = data.compatible
  const reason = typeof data.comparable_reason === 'string' ? data.comparable_reason : null
  if (typeof compatible !== 'boolean') return null
  const vaDisplay = va === null || va === undefined ? '1' : String(va)
  const vbDisplay = vb === null || vb === undefined ? '1' : String(vb)
  return (
    <div className="mt-3 flex flex-wrap gap-2 text-xs">
      <span className="rounded-md bg-muted px-2 py-1 font-mono">V_a={vaDisplay}</span>
      <span className="rounded-md bg-muted px-2 py-1 font-mono">V_b={vbDisplay}</span>
      <span className="rounded-md bg-muted px-2 py-1 font-mono">
        compatible={String(compatible)}
      </span>
      {!compatible && reason && (
        <span className="rounded-md bg-muted px-2 py-1 font-mono">reason={reason}</span>
      )}
    </div>
  )
}

/* ===========================================================================
 * PRP-40 — planning + knowledge mini summaries
 * =========================================================================== */

function formatSignedNumber(value: unknown, fractionDigits = 1): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'n/a'
  return value >= 0 ? `+${value.toFixed(fractionDigits)}` : value.toFixed(fractionDigits)
}

/** scenario_simulate_and_save — plan name + method + Δunits + Δrevenue. */
function ScenarioSummary({ data }: { data: Record<string, unknown> }) {
  const scenarioId = typeof data.scenario_id === 'string' ? data.scenario_id : null
  const method = typeof data.method === 'string' ? data.method : null
  if (!scenarioId && !method) return null
  return (
    <div className="mt-3 flex flex-wrap gap-2 text-xs">
      <span className="rounded-md bg-muted px-2 py-1 font-mono">
        plan: showcase-price-cut-10pct
      </span>
      {method && (
        <span className="rounded-md bg-muted px-2 py-1 font-mono">method: {method}</span>
      )}
      <span className="rounded-md bg-muted px-2 py-1 font-mono">
        Δunits: {formatSignedNumber(data.units_delta, 1)}
      </span>
      <span className="rounded-md bg-muted px-2 py-1 font-mono">
        Δrevenue: {formatSignedNumber(data.revenue_delta, 2)}
      </span>
    </div>
  )
}

/** multi_plan_compare — winner + ranked_by + per-plan deltas. */
function CompareSummary({ data }: { data: Record<string, unknown> }) {
  const winnerName = typeof data.winner_name === 'string' ? data.winner_name : null
  const rankedBy = typeof data.ranked_by === 'string' ? data.ranked_by : null
  const rankedRaw = data.ranked
  const ranked = Array.isArray(rankedRaw) ? rankedRaw : []
  if (!winnerName && ranked.length === 0) return null
  return (
    <div className="mt-3 space-y-1">
      <div className="flex flex-wrap gap-2 text-xs">
        {winnerName && (
          <span className="rounded-md bg-success/10 px-2 py-1 font-mono font-semibold">
            🏆 winner: {winnerName}
          </span>
        )}
        {rankedBy && (
          <span className="rounded-md bg-muted px-2 py-1 font-mono">
            ranked_by: {rankedBy}
          </span>
        )}
      </div>
      <div className="space-y-1">
        {ranked.map((row, idx) => {
          if (!row || typeof row !== 'object') return null
          const r = row as Record<string, unknown>
          const name = typeof r.name === 'string' ? r.name : `plan-${idx}`
          const unitsDelta = r.units_delta
          const revenueDelta = r.revenue_delta
          return (
            <div
              key={`${name}-${idx}`}
              className="flex items-center justify-between rounded-md bg-muted px-2 py-1 text-xs"
            >
              <span className="font-mono">{name}</span>
              <span className="font-mono">
                Δunits {formatSignedNumber(unitsDelta, 1)} ·
                Δrev {formatSignedNumber(revenueDelta, 2)}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** embedding_provider_probe — provider chip + reachable badge. */
function ProviderChip({ data }: { data: Record<string, unknown> }) {
  const provider = typeof data.provider === 'string' ? data.provider : null
  const reachable = data.reachable === true
  if (!provider) return null
  return (
    <div className="mt-3 flex flex-wrap gap-2 text-xs">
      <span className="rounded-md bg-muted px-2 py-1 font-mono">provider: {provider}</span>
      <span
        className={cn(
          'rounded-md px-2 py-1 font-mono',
          reachable ? 'bg-success/10' : 'bg-warning/10'
        )}
      >
        {reachable ? '✅ reachable' : '⏭️ unreachable'}
      </span>
    </div>
  )
}

/** rag_index_subset — curated_hits/5 + chunks + failed. */
function IndexSummary({ data }: { data: Record<string, unknown> }) {
  const curatedHits = typeof data.curated_hits === 'number' ? data.curated_hits : null
  const totalChunks = typeof data.total_chunks === 'number' ? data.total_chunks : null
  const failed = typeof data.failed === 'number' ? data.failed : null
  if (curatedHits === null && totalChunks === null) return null
  return (
    <div className="mt-3 flex flex-wrap gap-2 text-xs">
      {curatedHits !== null && (
        <span className="rounded-md bg-muted px-2 py-1 font-mono">
          files: {curatedHits}/5
        </span>
      )}
      {totalChunks !== null && (
        <span className="rounded-md bg-muted px-2 py-1 font-mono">
          chunks: {totalChunks}
        </span>
      )}
      {failed !== null && failed > 0 && (
        <span className="rounded-md bg-destructive/10 px-2 py-1 font-mono">
          failed: {failed}
        </span>
      )}
    </div>
  )
}

/** PRP-39 — stale-alias trigger mini-summary chip-line. */
function StaleAliasDetail({ data }: { data: Record<string, unknown> }) {
  const aliasName = typeof data.alias_name === 'string' ? data.alias_name : null
  const staleReason = typeof data.stale_reason === 'string' ? data.stale_reason : null
  const aliasV = data.alias_feature_frame_version
  const comparableV = data.comparable_run_feature_frame_version
  if (!aliasName || !staleReason) return null
  return (
    <div className="mt-3 flex flex-wrap gap-2 text-xs">
      <span className="rounded-md bg-muted px-2 py-1 font-mono">alias={aliasName}</span>
      <span className="rounded-md bg-muted px-2 py-1 font-mono">
        stale_reason={staleReason}
      </span>
      <span className="rounded-md bg-muted px-2 py-1 font-mono">
        V_alias={String(aliasV ?? 'null')} → V_comparable={String(comparableV ?? 'null')}
      </span>
    </div>
  )
}

/** PRP-39 — safer-Promote flow mini-summary chip-line. */
function SaferPromoteDetail({ data }: { data: Record<string, unknown> }) {
  const aliasName = typeof data.alias_name === 'string' ? data.alias_name : null
  const before = typeof data.before_run_id === 'string' ? data.before_run_id : null
  const after = typeof data.after_run_id === 'string' ? data.after_run_id : null
  if (!aliasName || !before || !after) return null
  return (
    <div className="mt-3 flex flex-wrap gap-2 text-xs">
      <span className="rounded-md bg-muted px-2 py-1 font-mono">alias={aliasName}</span>
      <span className="rounded-md bg-muted px-2 py-1 font-mono">
        before={before.slice(0, 8)} → after={after.slice(0, 8)}
      </span>
    </div>
  )
}

/** PRP-39 — batch preset mini-summary chip-line. */
function BatchPresetDetail({ data }: { data: Record<string, unknown> }) {
  const presetSource = typeof data.preset_source === 'string' ? data.preset_source : null
  const completed = data.completed_items
  const total = data.total_items
  const status = typeof data.status === 'string' ? data.status : null
  if (!presetSource || !status) return null
  return (
    <div className="mt-3 flex flex-wrap gap-2 text-xs">
      <span className="rounded-md bg-muted px-2 py-1 font-mono">preset={presetSource}</span>
      <span className="rounded-md bg-muted px-2 py-1 font-mono">
        {String(completed ?? '?')}/{String(total ?? '?')} done
      </span>
      <span className="rounded-md bg-muted px-2 py-1 font-mono">status={status}</span>
    </div>
  )
}

/** rag_retrieve_probe — top hit title + similarity score. */
function RetrieveSummary({ data }: { data: Record<string, unknown> }) {
  const topSource = typeof data.top_source_path === 'string' ? data.top_source_path : null
  const score = typeof data.top_relevance_score === 'number' ? data.top_relevance_score : null
  if (!topSource) return null
  return (
    <div className="mt-3 flex flex-wrap gap-2 text-xs">
      <span className="rounded-md bg-muted px-2 py-1 font-mono">top: {topSource}</span>
      {score !== null && (
        <span className="rounded-md bg-muted px-2 py-1 font-mono">
          score: {score.toFixed(3)}
        </span>
      )}
    </div>
  )
}

interface DemoStepCardProps {
  step: DemoStep
  index: number
  /** Optional deep-link href; rendered as an Inspect button on terminal pass. */
  inspectHref?: string | null
}

/** One pipeline step rendered as a status card. */
export function DemoStepCard({ step, index, inspectHref }: DemoStepCardProps) {
  const duration = formatDuration(step.durationMs)
  // PRP-38 — bucketed metrics ride alongside per_model on the backtest step
  // when the SHOWCASE_RICH path is active (main model is feature-aware).
  const bucketed = step.data.bucketed_aggregated_metrics as
    | Record<string, Record<string, number>>
    | undefined
  const showInspect = step.status === 'pass' && typeof inspectHref === 'string' && inspectHref
  return (
    <Card
      className={cn(
        'border-l-4 p-4 transition-colors',
        STATUS_ACCENT[step.status],
        step.status === 'idle' && 'opacity-60'
      )}
    >
      <div className="flex items-start gap-3">
        <span
          className={cn('text-lg leading-none', step.status === 'running' && 'animate-pulse')}
          aria-hidden
        >
          {STATUS_GLYPH[step.status]}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2">
            <p className="font-medium">
              <span className="text-muted-foreground">
                {String(index + 1).padStart(2, '0')}.
              </span>{' '}
              {step.label}
            </p>
            {duration && (
              <span className="shrink-0 font-mono text-xs text-muted-foreground">
                {duration}
              </span>
            )}
          </div>
          {step.detail && (
            <p className="mt-1 break-words text-sm text-muted-foreground">{step.detail}</p>
          )}
          {step.name === 'backtest' && <BacktestBreakdown data={step.data} />}
          {step.name === 'backtest' && bucketed && (
            <HorizonBucketsMini bucketed={bucketed} />
          )}
          {step.name === 'register' && <RegisterDetail data={step.data} />}
          {/* PRP-39 — terminal-pass mini-summaries for the 4 new step kinds. */}
          {step.name === 'champion_compat_compare' && (
            <ChampionCompatDetail data={step.data} />
          )}
          {step.name === 'stale_alias_trigger' && <StaleAliasDetail data={step.data} />}
          {step.name === 'safer_promote_flow' && <SaferPromoteDetail data={step.data} />}
          {step.name === 'batch_preset' && <BatchPresetDetail data={step.data} />}
          {/* PRP-40 — planning + knowledge mini summaries. */}
          {step.name === 'scenario_simulate_and_save' && (
            <ScenarioSummary data={step.data} />
          )}
          {step.name === 'multi_plan_compare' && <CompareSummary data={step.data} />}
          {step.name === 'embedding_provider_probe' && (
            <ProviderChip data={step.data} />
          )}
          {step.name === 'rag_index_subset' && <IndexSummary data={step.data} />}
          {step.name === 'rag_retrieve_probe' && <RetrieveSummary data={step.data} />}
          {showInspect && (
            <div className="mt-3">
              <Button asChild variant="outline" size="sm">
                <Link to={inspectHref}>
                  Inspect
                  <ArrowUpRight className="ml-1 h-3 w-3" />
                </Link>
              </Button>
            </div>
          )}
        </div>
      </div>
    </Card>
  )
}
