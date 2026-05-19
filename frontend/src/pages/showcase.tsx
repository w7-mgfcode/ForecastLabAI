import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Play, Loader2, Trophy, AlertTriangle, ArrowRight } from 'lucide-react'
import { useDemoPipeline } from '@/hooks/use-demo-pipeline'
import { DemoStepCard } from '@/components/demo'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { ROUTES } from '@/lib/constants'
import { cn } from '@/lib/utils'

const TERMINAL_STATUSES = new Set(['pass', 'fail', 'skip', 'warn'])

export default function ShowcasePage() {
  const { steps, phase, summary, errorMessage, isRunning, connectionStatus, start } =
    useDemoPipeline()
  const [reseed, setReseed] = useState(false)
  const [resetDb, setResetDb] = useState(false)

  const completed = steps.filter((s) => TERMINAL_STATUSES.has(s.status)).length

  const handleRun = () => {
    start({ seed: 42, skip_seed: !reseed, reset: resetDb })
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">End-to-End Showcase</h1>
        <p className="mt-1 text-muted-foreground">
          Run the full forecasting pipeline live — seed → features → train ×3 → backtest ×3 →
          register the winning model → verify → agent. The same flow as{' '}
          <code className="rounded bg-muted px-1 py-0.5 text-sm">make demo</code>, streamed to
          the browser.
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
                : 'Drives the published API in-process. Takes ~30–60 s on a seeded database.'}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-6">
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

      {/* Step cards */}
      <div className="space-y-3">
        {steps.map((step, index) => (
          <DemoStepCard key={step.name} step={step} index={index} />
        ))}
      </div>
    </div>
  )
}
