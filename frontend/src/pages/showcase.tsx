import { Link } from 'react-router-dom'
import { Play, Loader2, Trophy, AlertTriangle, ArrowRight, Square } from 'lucide-react'
import { useState } from 'react'
import { useDemoPipeline } from '@/hooks/use-demo-pipeline'
import type { DemoStep } from '@/hooks/use-demo-pipeline'
import { useWorkspace } from '@/hooks/use-workspaces'
import { DemoPhasePanel } from '@/components/demo/DemoPhasePanel'
import { ScenarioPicker } from '@/components/demo/ScenarioPicker'
import { ShowcaseKpiStrip } from '@/components/demo/ShowcaseKpiStrip'
import { InspectArtifactsPanel } from '@/components/demo/InspectArtifactsPanel'
import { RunHistoryStrip } from '@/components/demo/RunHistoryStrip'
import { WorkspacePanel } from '@/components/demo/WorkspacePanel'
import { WorkspaceArtifactsPanel } from '@/components/demo/WorkspaceArtifactsPanel'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { ROUTES } from '@/lib/constants'
import { cn } from '@/lib/utils'
import type { WorkspaceListItem } from '@/types/api'

const TERMINAL_STATUSES = new Set(['pass', 'fail', 'skip', 'warn'])

// E4 (#393) — mirrors the backend DemoRunRequest.workspace_name pattern
// (schemas.py): lowercase letters/digits, then -/_ allowed; ≤100 chars.
const WORKSPACE_NAME_PATTERN = /^[a-z0-9][a-z0-9\-_]*$/

/**
 * PRP-38 / PRP-39 / PRP-40 — resolve the per-step Inspect deep link.
 *
 * Returns null when the step has no payload to inspect; the step card
 * suppresses the button. Targets:
 * - `train`                         -> /visualize/forecast (store_id + product_id from step.data)
 * - `v2_train`                      -> /explorer/runs/{v2_run_id} (Feature Frame panel)
 * - `register`                      -> /explorer/runs/{run_id} (the winner)
 * - `backtest`                      -> /visualize/backtest (store_id + product_id from ctx)
 * - `champion_compat_compare`       -> /explorer/runs/compare?a={v1}&b={v2}   (PRP-39)
 * - `stale_alias_trigger`           -> /ops                                    (PRP-39)
 * - `safer_promote_flow`            -> /ops                                    (PRP-39)
 * - `batch_preset`                  -> /visualize/batch/{batch_id}             (PRP-39)
 * - `scenario_simulate_and_save`    -> /visualize/planner?scenario_id={id}     (PRP-40)
 * - `multi_plan_compare`            -> /visualize/planner                      (PRP-40)
 * - `embedding_provider_probe`      -> /admin                                  (PRP-40)
 * - `rag_index_subset`              -> /knowledge                              (PRP-40)
 * - `rag_retrieve_probe`            -> /knowledge                              (PRP-40)
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
    case 'scenario_simulate_and_save': {
      const scenarioId = typeof data.scenario_id === 'string' ? data.scenario_id : null
      return scenarioId
        ? `${ROUTES.VISUALIZE.PLANNER}?scenario_id=${scenarioId}`
        : ROUTES.VISUALIZE.PLANNER
    }
    case 'multi_plan_compare':
      return ROUTES.VISUALIZE.PLANNER
    case 'embedding_provider_probe':
      return ROUTES.ADMIN
    case 'rag_index_subset':
    case 'rag_retrieve_probe':
      return ROUTES.KNOWLEDGE
    // PRP-41 — HITL flow + ops snapshot.
    case 'agent_hitl_flow':
      return ROUTES.CHAT
    case 'ops_snapshot':
      return ROUTES.OPS
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
    stop,
    scenario,
    setScenario,
  } = useDemoPipeline()
  const [reseed, setReseed] = useState(false)
  const [resetDb, setResetDb] = useState(false)
  // E4 (#393) — workspace controls + restore state.
  const [seed, setSeed] = useState(42)
  const [keepWorkspace, setKeepWorkspace] = useState(false)
  const [workspaceName, setWorkspaceName] = useState('')
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | null>(null)

  // The page (not the panel) resolves the loaded workspace's detail — the
  // artifacts panel needs detail-only created_objects.
  const { data: loadedWorkspace } = useWorkspace(
    selectedWorkspaceId ?? '',
    !!selectedWorkspaceId
  )

  const completed = steps.filter((s) => TERMINAL_STATUSES.has(s.status)).length

  const trimmedName = workspaceName.trim()
  const nameInvalid =
    keepWorkspace && trimmedName !== '' && !WORKSPACE_NAME_PATTERN.test(trimmedName)

  const handleRun = () => {
    // Starting a run detaches any loaded workspace — live cards take over.
    setSelectedWorkspaceId(null)
    start({
      seed,
      skip_seed: !reseed,
      reset: resetDb,
      scenario,
      // Omit the preservation fields entirely on ephemeral runs (legacy
      // byte-compat); omit workspace_name when the input is empty.
      ...(keepWorkspace
        ? {
            preservation: 'keep' as const,
            ...(trimmedName ? { workspace_name: trimmedName } : {}),
          }
        : {}),
    })
  }

  // E4 (#393) — Load: recorded config repopulates the controls; the detail
  // query then renders the artifacts panel. Read-only — no run starts.
  const handleLoadWorkspace = (ws: WorkspaceListItem) => {
    setScenario(ws.scenario)
    setSeed(ws.seed)
    setReseed(!ws.skip_seed)
    setResetDb(ws.reset)
    setKeepWorkspace(true)
    setWorkspaceName(ws.name ?? '')
    setSelectedWorkspaceId(ws.workspace_id)
  }

  // E4 (#393) — Replay: Load, then re-submit the recorded config VERBATIM
  // through the existing WS run path with preservation='keep' (a replay is
  // itself a workspace run). setScenario runs first (picker-desync gotcha:
  // start() does not sync the picker state).
  const handleReplayWorkspace = (ws: WorkspaceListItem) => {
    handleLoadWorkspace(ws)
    // The re-run's live cards take over; the original row stays untouched.
    setSelectedWorkspaceId(null)
    start({
      seed: ws.seed,
      scenario: ws.scenario,
      reset: ws.reset,
      skip_seed: ws.skip_seed,
      preservation: 'keep',
      ...(ws.name ? { workspace_name: ws.name } : {}),
    })
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
          the browser. Pick a scenario to control depth and data shape — all eight seeder
          presets are available (demo_minimal stays fast; showcase_rich exercises V1+V2
          modeling).
        </p>
      </div>

      {/* PRP-41 — KPI strip at the top, hidden until at least one step completes. */}
      <ShowcaseKpiStrip steps={steps} />

      {/* PRP-41 — Replayable run history (localStorage FIFO 5; ephemeral runs only). */}
      <RunHistoryStrip
        onReplay={(req) => start(req)}
        summary={phase === 'done' ? summary : null}
        scenario={scenario}
      />

      {/* E4 (#393) — server-backed saved workspaces (Load + Replay). */}
      <WorkspacePanel
        onLoad={handleLoadWorkspace}
        onReplay={handleReplayWorkspace}
        isRunning={isRunning}
        lastWorkspaceId={summary?.workspaceId ?? null}
      />

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
            <Button onClick={handleRun} disabled={isRunning || nameInvalid} size="lg">
              {isRunning ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Play className="mr-2 h-4 w-4" />
              )}
              {isRunning ? 'Running…' : 'Run pipeline'}
            </Button>

            {/* PRP-41 — Stop button: cancel an in-flight pipeline. */}
            {isRunning && (
              <Button onClick={stop} variant="outline" size="lg">
                <Square className="mr-2 h-4 w-4" />
                Stop
              </Button>
            )}

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

            {/* E4 (#393) — controllable seed (restore is meaningless without it). */}
            <label className="flex items-center gap-2 text-sm">
              <span>Seed</span>
              <Input
                type="number"
                min={0}
                className="h-9 w-24"
                value={seed}
                onChange={(e) => {
                  const next = Number.parseInt(e.target.value, 10)
                  setSeed(Number.isNaN(next) || next < 0 ? 0 : next)
                }}
                disabled={isRunning}
              />
            </label>

            {/* E4 (#393) — preservation controls. */}
            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={keepWorkspace}
                onCheckedChange={(v) => setKeepWorkspace(v === true)}
                disabled={isRunning}
              />
              <span>
                Save as workspace
                <span className="ml-1 text-muted-foreground">(keeps this run restorable)</span>
              </span>
            </label>

            {keepWorkspace && (
              <div className="flex flex-col gap-1 text-sm">
                <label className="flex items-center gap-2">
                  <span>Name</span>
                  <Input
                    className="h-9 w-48"
                    placeholder="optional, e.g. black-friday"
                    value={workspaceName}
                    onChange={(e) => setWorkspaceName(e.target.value)}
                    disabled={isRunning}
                    maxLength={100}
                    aria-invalid={nameInvalid}
                  />
                </label>
                {nameInvalid && (
                  <p className="text-xs text-destructive">
                    Lowercase letters/digits only, then “-” or “_” (must not start with either).
                  </p>
                )}
              </div>
            )}
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

      {/* PRP-41 — post-run deep-link grid (10 cards). */}
      {phase === 'done' && summary && (
        <InspectArtifactsPanel steps={steps} summary={summary} />
      )}

      {/* E4 (#393) — re-attached artifacts of a LOADED workspace. Any started
          run detaches it (selectedWorkspaceId cleared) so live cards take over. */}
      {phase !== 'running' && loadedWorkspace && (
        <WorkspaceArtifactsPanel workspace={loadedWorkspace} />
      )}
    </div>
  )
}
