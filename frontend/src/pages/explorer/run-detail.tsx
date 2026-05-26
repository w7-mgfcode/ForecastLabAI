import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { format } from 'date-fns'
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  GitCompare,
  Loader2,
  ShieldCheck,
} from 'lucide-react'
import { useRun, useVerifyArtifact } from '@/hooks/use-runs'
import { useRunExplanation } from '@/hooks/use-explanations'
import { useRunFeatureMetadata } from '@/hooks/use-feature-metadata'
import { ExplanationPanel } from '@/components/explainability/explanation-panel'
import { FeatureImportancePanel } from '@/components/explainability/feature-importance-panel'
import { FeatureFramePanel } from '@/components/forecast-intelligence/feature-frame-panel'
import { JsonBlock } from '@/components/common/json-block'
import { ErrorDisplay } from '@/components/common/error-display'
import { LoadingState } from '@/components/common/loading-state'
import { ModelFamilyBadge } from '@/components/common/model-family-badge'
import { StatusBadge } from '@/components/common/status-badge'
import { getStatusVariant } from '@/lib/status-utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { formatNumber, getErrorMessage } from '@/lib/api'
import { ROUTES } from '@/lib/constants'

function fmtDate(value: string | null | undefined): string {
  return value ? format(new Date(value), 'MMM d, yyyy HH:mm') : '—'
}

function Field({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={mono ? 'break-all font-mono text-sm' : 'font-medium'}>{value}</dd>
    </div>
  )
}

export default function RunDetailPage() {
  const { runId } = useParams()
  const runQuery = useRun(runId ?? '', !!runId)

  // The verify GET is button-gated: disabled until the first click, then refetch.
  const [verifyOn, setVerifyOn] = useState(false)
  const verifyQuery = useVerifyArtifact(runId ?? '', verifyOn)

  // The explanation panel self-handles a 400 for non-baseline (lightgbm) runs.
  const explanationQuery = useRunExplanation(runId ?? '', !!runId)

  // MLZOO-D / PRP-31 — load the new feature-metadata only for non-baseline
  // runs. `enabled: false` makes TanStack Query skip the fetch entirely, so
  // baseline runs render nothing extra and never see the 400 burst the panel
  // would otherwise have to swallow.
  const featureMetaQuery = useRunFeatureMetadata(
    runId ?? '',
    !!runId && runQuery.data?.model_family !== undefined &&
      runQuery.data?.model_family !== 'baseline',
  )

  if (!runId) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Run Detail</h1>
        <ErrorDisplay error={new Error('No run id in the URL.')} title="Invalid run" />
      </div>
    )
  }

  if (runQuery.error) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Run Detail</h1>
        <ErrorDisplay error={runQuery.error} onRetry={() => void runQuery.refetch()} />
      </div>
    )
  }

  if (runQuery.isLoading || !runQuery.data) {
    return <LoadingState message="Loading run..." />
  }

  const run = runQuery.data

  function handleVerify() {
    if (!verifyOn) setVerifyOn(true)
    else void verifyQuery.refetch()
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="space-y-1">
          <Button asChild variant="ghost" size="sm" className="-ml-2 h-7">
            <Link to={ROUTES.EXPLORER.RUNS}>
              <ArrowLeft className="mr-1 h-4 w-4" />
              Back to Model Runs
            </Link>
          </Button>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="break-all font-mono text-2xl font-bold">{run.run_id}</h1>
            <StatusBadge variant={getStatusVariant(run.status)}>{run.status}</StatusBadge>
            <ModelFamilyBadge family={run.model_family} />
          </div>
          <p className="text-sm text-muted-foreground">{run.model_type}</p>
        </div>
        <Button asChild variant="outline">
          <Link to={`${ROUTES.EXPLORER.RUN_COMPARE}?a=${run.run_id}`}>
            <GitCompare className="mr-2 h-4 w-4" />
            Compare with…
          </Link>
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Run profile</CardTitle>
          <CardDescription>Registry record for this model run.</CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            <Field label="Model type" value={run.model_type} />
            <div>
              <dt className="text-xs text-muted-foreground">Family</dt>
              <dd className="font-medium">
                <ModelFamilyBadge family={run.model_family} />
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Store</dt>
              <dd className="font-medium">
                <Link
                  className="text-primary hover:underline"
                  to={`/explorer/stores/${run.store_id}`}
                >
                  #{run.store_id}
                </Link>
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Product</dt>
              <dd className="font-medium">
                <Link
                  className="text-primary hover:underline"
                  to={`/explorer/products/${run.product_id}`}
                >
                  #{run.product_id}
                </Link>
              </dd>
            </div>
            <Field
              label="Data window"
              value={`${run.data_window_start} → ${run.data_window_end}`}
            />
            <Field label="Config hash" value={run.config_hash} mono />
            <Field label="Git SHA" value={run.git_sha ?? '—'} mono />
            <Field label="Created" value={fmtDate(run.created_at)} />
            <Field label="Started" value={fmtDate(run.started_at)} />
            <Field label="Completed" value={fmtDate(run.completed_at)} />
          </dl>
        </CardContent>
      </Card>

      {/* PRP-37 — Feature frame panel: surfaces V1/V2 + feature_groups +
          per-column safety classes. Empty-state for pre-PRP-35 runs. */}
      <FeatureFramePanel
        feature_frame_version={run.feature_frame_version}
        feature_groups={run.feature_groups}
        feature_safety_classes={featureMetaQuery.data?.feature_safety_classes}
        isLoading={featureMetaQuery.isLoading}
      />

      {run.status === 'failed' && run.error_message && (
        <Card className="border-destructive/50">
          <CardHeader>
            <CardTitle className="text-destructive">Error</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-destructive/90">{run.error_message}</p>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Metrics</CardTitle>
          <CardDescription>Evaluation metrics recorded for this run.</CardDescription>
        </CardHeader>
        <CardContent>
          <JsonBlock value={run.metrics} />
        </CardContent>
      </Card>

      <ExplanationPanel
        explanation={explanationQuery.data}
        isLoading={explanationQuery.isLoading}
        error={explanationQuery.error}
      />

      {run.model_family !== 'baseline' && (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                Feature Metadata
                <ModelFamilyBadge family={run.model_family} />
              </CardTitle>
              <CardDescription>
                The canonical 14-column feature frame the model consumed at
                training time.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {featureMetaQuery.isLoading ? (
                <LoadingState message="Loading feature metadata..." />
              ) : featureMetaQuery.data ? (
                <>
                  <ul className="flex flex-wrap gap-1.5">
                    {featureMetaQuery.data.feature_columns.map((name) => (
                      <li
                        key={name}
                        className="rounded-md border bg-muted/40 px-2 py-0.5 font-mono text-xs"
                      >
                        {name}
                      </li>
                    ))}
                  </ul>
                  {featureMetaQuery.data.importance_type && (
                    <p className="mt-3 text-xs text-muted-foreground">
                      Importance type:{' '}
                      <span className="font-mono">
                        {featureMetaQuery.data.importance_type}
                      </span>
                    </p>
                  )}
                </>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Feature metadata unavailable for this run.
                </p>
              )}
            </CardContent>
          </Card>

          <FeatureImportancePanel
            data={featureMetaQuery.data}
            isLoading={featureMetaQuery.isLoading}
            error={featureMetaQuery.error}
          />
        </>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Model config</CardTitle>
          </CardHeader>
          <CardContent>
            <JsonBlock value={run.model_config} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Feature config</CardTitle>
          </CardHeader>
          <CardContent>
            <JsonBlock value={run.feature_config} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Runtime info</CardTitle>
          <CardDescription>Environment captured at training time.</CardDescription>
        </CardHeader>
        <CardContent>
          <JsonBlock value={run.runtime_info} />
        </CardContent>
      </Card>

      {run.agent_context && (
        <Card>
          <CardHeader>
            <CardTitle>Agent context</CardTitle>
            <CardDescription>The agent session that created this run.</CardDescription>
          </CardHeader>
          <CardContent>
            <JsonBlock value={run.agent_context} />
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Artifact</CardTitle>
          <CardDescription>Stored model artifact and SHA-256 integrity check.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <dl className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Field label="Artifact URI" value={run.artifact_uri ?? '—'} mono />
            <Field label="Artifact hash" value={run.artifact_hash ?? '—'} mono />
            <Field
              label="Size"
              value={
                run.artifact_size_bytes != null
                  ? `${formatNumber(run.artifact_size_bytes)} bytes`
                  : '—'
              }
            />
          </dl>

          <div className="flex items-center gap-3">
            <Button onClick={handleVerify} disabled={!run.artifact_uri || verifyQuery.isFetching}>
              {verifyQuery.isFetching ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <ShieldCheck className="mr-2 h-4 w-4" />
              )}
              Verify integrity
            </Button>
            {!run.artifact_uri && (
              <span className="text-sm text-muted-foreground">This run has no artifact.</span>
            )}
          </div>

          {verifyOn && !verifyQuery.isFetching && verifyQuery.error && (
            <div className="flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{getErrorMessage(verifyQuery.error)}</span>
            </div>
          )}

          {verifyOn &&
            !verifyQuery.isFetching &&
            verifyQuery.data &&
            (verifyQuery.data.verified ? (
              <div className="flex items-start gap-2 rounded-md border border-success/30 bg-success/10 p-3 text-sm text-foreground">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                <span>
                  Artifact verified — the stored checksum matches.
                  {verifyQuery.data.computed_hash && (
                    <span className="block break-all font-mono text-xs">
                      {verifyQuery.data.computed_hash}
                    </span>
                  )}
                </span>
              </div>
            ) : (
              <div className="flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>
                  Integrity check failed — the artifact does not match its stored hash.
                  {verifyQuery.data.error && (
                    <span className="block text-xs">{verifyQuery.data.error}</span>
                  )}
                </span>
              </div>
            ))}
        </CardContent>
      </Card>
    </div>
  )
}
