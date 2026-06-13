import { ArrowUpRight } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import type { DemoStep, DemoStepUiStatus } from '@/hooks/use-demo-pipeline'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { api, ApiError } from '@/lib/api'
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

/** PRP-41 — HITL flow mini-summary (session/tokens/tool_calls/approval chips). */
function HitlFlowSummary({ data }: { data: Record<string, unknown> }) {
  const sessionId = typeof data.session_id === 'string' ? data.session_id : ''
  const tokens =
    typeof data.tokens_used === 'number' ? data.tokens_used : Number(data.tokens_used ?? 0)
  const toolCalls =
    typeof data.tool_calls_count === 'number'
      ? data.tool_calls_count
      : Number(data.tool_calls_count ?? 0)
  const decision =
    typeof data.approval_decision === 'string' ? data.approval_decision : ''
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
      {sessionId && (
        <span className="rounded-md bg-muted px-2 py-1 font-mono">
          session={sessionId.slice(0, 8)}...
        </span>
      )}
      <span className="rounded-md bg-muted px-2 py-1 font-mono">tokens={tokens}</span>
      <span className="rounded-md bg-muted px-2 py-1 font-mono">
        tool_calls={toolCalls}
      </span>
      {decision && (
        <span className="rounded-md bg-primary/10 px-2 py-1 font-mono">
          approval={decision}
        </span>
      )}
    </div>
  )
}

/** PRP-41 — ops snapshot 5-tile KPI grid. */
function OpsSnapshotMiniGrid({ data }: { data: Record<string, unknown> }) {
  const tiles: ReadonlyArray<readonly [string, unknown]> = [
    ['stale_aliases', data.stale_aliases_count],
    ['retraining', data.retraining_candidates_count],
    ['runs', data.total_runs],
    ['aliases', data.total_aliases],
    ['degrading', data.degrading_health_count],
  ]
  return (
    <div className="mt-3 grid grid-cols-5 gap-2 text-xs">
      {tiles.map(([label, value]) => (
        <div key={label} className="rounded-md border p-2 text-center">
          <div className="text-muted-foreground">{label}</div>
          <div className="font-mono font-semibold">
            {value !== undefined && value !== null ? String(value) : '—'}
          </div>
        </div>
      ))}
    </div>
  )
}

/**
 * E5 (#411) — Approve / Reject buttons rendered on the HITL step card while
 * the backend awaits a decision (`awaiting_approval=true` + `status='running'`).
 *
 * Either click relays the operator's intent to the DEMO slice via
 * `POST /demo/hitl-decision` (through `lib/api.ts` `api()` — API_BASE_URL
 * prefixed, never bare `fetch`, so it works off-origin). The pipeline is the
 * sole caller of the agents approve endpoint. Both buttons disable after
 * either click. A live "auto-approve in Ns" countdown reads the backend's
 * `decision_window_s` (fallback 10) — never hardcoded, never derived from the
 * 90 s hard timeout. 404/409 are absorbed silently (the auto-approve raced);
 * only 5xx surfaces an inline error.
 */
function HitlDecisionButtons({
  actionId,
  decisionWindowS,
}: {
  actionId: string
  decisionWindowS: number
}) {
  const [pending, setPending] = useState<'approved' | 'rejected' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [remaining, setRemaining] = useState(Math.max(0, Math.ceil(decisionWindowS)))

  useEffect(() => {
    if (pending) return
    const id = setInterval(() => {
      setRemaining((prev) => (prev > 0 ? prev - 1 : 0))
    }, 1000)
    return () => clearInterval(id)
  }, [pending])

  const decide = async (decision: 'approved' | 'rejected') => {
    if (pending || !actionId) return
    setPending(decision)
    try {
      await api<void>('/demo/hitl-decision', {
        method: 'POST',
        body: { action_id: actionId, decision },
      })
    } catch (err) {
      // Absorb 404 (no pending action) / 409 (already decided) — the
      // auto-approve or a prior click raced. Surface only 5xx.
      if (err instanceof ApiError && err.status >= 500) {
        setError(`decision failed (${err.status})`)
      } else if (!(err instanceof ApiError)) {
        setError(err instanceof Error ? err.message : 'decision failed')
      }
    }
  }

  return (
    <div className="mt-3 flex flex-wrap items-center gap-3">
      <Button
        onClick={() => void decide('approved')}
        disabled={pending !== null}
        size="sm"
        variant="default"
      >
        {pending === 'approved' ? 'Approving…' : 'Approve'}
      </Button>
      <Button
        onClick={() => void decide('rejected')}
        disabled={pending !== null}
        size="sm"
        variant="destructive"
      >
        {pending === 'rejected' ? 'Rejecting…' : 'Reject'}
      </Button>
      {!pending && (
        <span className="text-xs text-muted-foreground">
          auto-approve in {remaining}s
        </span>
      )}
      {error && <span className="text-xs text-destructive">{error}</span>}
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
          {/* PRP-41 — agents (HITL) + ops snapshot mini-summaries. */}
          {step.name === 'agent_hitl_flow' && <HitlFlowSummary data={step.data} />}
          {step.name === 'ops_snapshot' && <OpsSnapshotMiniGrid data={step.data} />}
          {/* E5 (#411) — Approve / Reject only while awaiting (status==running);
              countdown reads data.decision_window_s (fallback 10). */}
          {step.data.awaiting_approval === true &&
            step.status === 'running' &&
            typeof step.data.action_id === 'string' && (
              <HitlDecisionButtons
                actionId={step.data.action_id}
                decisionWindowS={
                  typeof step.data.decision_window_s === 'number'
                    ? step.data.decision_window_s
                    : 10
                }
              />
            )}
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
