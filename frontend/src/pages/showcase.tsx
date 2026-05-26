import { Link } from 'react-router-dom'
import { Play, Loader2, Trophy, AlertTriangle, ArrowRight } from 'lucide-react'
import { useState } from 'react'
import { useDemoPipeline } from '@/hooks/use-demo-pipeline'
import type { DemoStep } from '@/hooks/use-demo-pipeline'
import { DemoPhasePanel } from '@/components/demo/DemoPhasePanel'
import { ScenarioPicker } from '@/components/demo/ScenarioPicker'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { ROUTES } from '@/lib/constants'
import { cn } from '@/lib/utils'

const TERMINAL_STATUSES = new Set(['pass', 'fail', 'skip', 'warn'])

/**
 * PRP-38/39 — resolve the per-step Inspect deep link.
 *
 * Returns null when the step has no payload to inspect; the step card
 * suppresses the button. Targets:
 * - `train`                    -> /visualize/forecast (store_id + product_id from step.data)
 * - `v2_train`                 -> /explorer/runs/{v2_run_id} (Feature Frame panel)
 * - `register`                 -> /explorer/runs/{run_id} (the winner)
 * - `backtest`                 -> /visualize/backtest (store_id + product_id from ctx)
 * - `champion_compat_compare`  -> /explorer/runs/compare?a={v1}&b={v2}   (PRP-39)
 * - `stale_alias_trigger`      -> /ops                                    (PRP-39)
 * - `safer_promote_flow`       -> /ops                                    (PRP-39)
 * - `batch_preset`             -> /visualize/batch/{batch_id}             (PRP-39)
 */
function resolveInspectHref(step: DemoStep): string | null {
  const data = step.data
  const storeId = typeof data.store_id === 'number' ? data.store_id : null
  const productId = typeof data.product_id === 'number' ? data.product_id : null
  const v2RunId = typeof data.v2_run_id === 'string' ? data.v2_run_id : null
  const runId = typeof data.run_id === 'string' ? data.run_id : null
  switch (step.name) {
    case 'train':
      if (storeId !== null && productId !== null) {
        return `${ROUTES.VISUALIZE.FORECAST}?store_id=${storeId}&product_id=${productId}`
      }
      return null
    case 'v2_train':
      return v2RunId ? `${ROUTES.EXPLORER.RUNS}/${v2RunId}` : null
    case 'register':
      return runId ? `${ROUTES.EXPLORER.RUNS}/${runId}` : null
    case 'backtest':
      if (storeId !== null && productId !== null) {
        return `${ROUTES.VISUALIZE.BACKTEST}?store_id=${storeId}&product_id=${productId}`
      }
      return null
    case 'champion_compat_compare': {
      const v1 = typeof data.v1_run_id === 'string' ? data.v1_run_id : null
      const v2 = typeof data.v2_run_id === 'string' ? data.v2_run_id : null
      return v1 && v2 ? `${ROUTES.EXPLORER.RUN_COMPARE}?a=${v1}&b=${v2}` : null
    }
    case 'stale_alias_trigger':
    case 'safer_promote_flow':
      return ROUTES.OPS
    case 'batch_preset': {
      const batchId = typeof data.batch_id === 'string' ? data.batch_id : null
      return batchId ? `${ROUTES.VISUALIZE.BATCH}/${batchId}` : null
    }
    default:
      return null
  }
}

export default function ShowcasePage() {
  const {
    steps,
    phases,
    runningPhase,
    phase,
    summary,
    errorMessage,
    isRunning,
    connectionStatus,
    start,
    scenario,
    setScenario,
  } = useDemoPipeline()
  const [reseed, setReseed] = useState(false)
  const [resetDb, setResetDb] = useState(false)

  const completed = steps.filter((s) => TERMINAL_STATUSES.has(s.status)).length

  const handleRun = () => {
    start({ seed: 42, skip_seed: !reseed, reset: resetDb, scenario })
  }

  // For the Inspect link to surface store_id/product_id on the train/backtest
  // cards, we forward those ids from the status step's data (read once after
  // it completes).
  const statusStep = steps.find((s) => s.name === 'status')
  const ctxStoreId =
    statusStep && typeof statusStep.data.store_id === 'number' ? statusStep.data.store_id : null
  const ctxProductId =
    statusStep && typeof statusStep.data.product_id === 'number'
      ? statusStep.data.product_id
      : null

  const getInspectHref = (step: DemoStep) => {
    // Augment the step's own data with the discovered grain when not already
    // present (status sets it; train/backtest don't always echo it).
    if (
      (step.name === 'train' || step.name === 'backtest') &&
      ctxStoreId !== null &&
      ctxProductId !== null
    ) {
      const augmented: DemoStep = {
        ...step,
        data: {
          ...step.data,
          store_id: ctxStoreId,
          product_id: ctxProductId,
        },
      }
      return resolveInspectHref(augmented)
    }
    return resolveInspectHref(step)
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">End-to-End Showcase</h1>
        <p className="mt-1 text-muted-foreground">
          Run the full forecasting pipeline live — phase by phase. The same flow as{' '}
          <code className="rounded bg-muted px-1 py-0.5 text-sm">make demo</code>, streamed to
          the browser. Pick a scenario to control depth (demo_minimal stays fast;
          showcase_rich exercises V1+V2 modeling).
        </p>
      </div>

      {/* Controls */}
      <Card>
        <CardHeader>
          <CardTitle>Run the pipeline</CardTitle>
          <CardDescription>
            {connectionStatus === 'connected'
              ? 'Streaming live…'
              : isRunning
                ? 'Connecting…'
                : 'Drives the published API in-process. Wall-clock budget depends on the scenario.'}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-end gap-6">
            <ScenarioPicker value={scenario} onChange={setScenario} disabled={isRunning} />
            <Button onClick={handleRun} disabled={isRunning} size="lg">
              {isRunning ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Play className="mr-2 h-4 w-4" />
              )}
              {isRunning ? 'Running…' : 'Run pipeline'}
            </Button>

            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={reseed}
                onCheckedChange={(v) => setReseed(v === true)}
                disabled={isRunning}
              />
              <span>
                Re-seed first
                <span className="ml-1 text-muted-foreground">(slow — regenerates data)</span>
              </span>
            </label>

            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={resetDb}
                onCheckedChange={(v) => setResetDb(v === true)}
                disabled={isRunning}
              />
              <span>
                Reset database
                <span className="ml-1 text-destructive">(destructive — wipes all data)</span>
              </span>
            </label>
          </div>

          {phase === 'running' && (
            <p className="text-sm text-muted-foreground">
              Step {completed} of {steps.length} complete…
            </p>
          )}
        </CardContent>
      </Card>

      {/* Error banner */}
      {phase === 'error' && (
        <Card className="border-l-4 border-l-red-500">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <AlertTriangle className="h-5 w-5 text-destructive" />
              Pipeline could not start
            </CardTitle>
            <CardDescription>{errorMessage}</CardDescription>
          </CardHeader>
        </Card>
      )}

      {/* Summary banner */}
      {phase === 'done' && summary && (
        <Card
          className={cn(
            'border-l-4',
            summary.overallStatus === 'pass' ? 'border-l-success' : 'border-l-destructive'
          )}
        >
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Trophy
                className={cn(
                  'h-5 w-5',
                  summary.overallStatus === 'pass' ? 'text-success' : 'text-destructive'
                )}
              />
              {summary.overallStatus === 'pass'
                ? 'Pipeline complete'
                : 'Pipeline finished with a failure'}
            </CardTitle>
            <CardDescription>
              {summary.winnerModelType ? (
                <>
                  Winning model{' '}
                  <span className="font-mono font-semibold">{summary.winnerModelType}</span>
                  {summary.winnerWape !== null && (
                    <> · WAPE {summary.winnerWape.toFixed(4)}</>
                  )}{' '}
                  · {summary.wallClockS.toFixed(0)} s wall-clock
                </>
              ) : (
                <>No winning model selected · {summary.wallClockS.toFixed(0)} s wall-clock</>
              )}
            </CardDescription>
          </CardHeader>
          {summary.winningRunId && (
            <CardContent>
              <Button asChild variant="outline" size="sm">
                <Link to={ROUTES.EXPLORER.RUNS}>
                  View model runs
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Link>
              </Button>
            </CardContent>
          )}
        </Card>
      )}

      {/* Phase accordion */}
      <DemoPhasePanel
        phases={phases}
        runningPhase={runningPhase}
        getInspectHref={getInspectHref}
      />
    </div>
  )
}
