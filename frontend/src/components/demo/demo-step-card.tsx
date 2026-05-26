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
