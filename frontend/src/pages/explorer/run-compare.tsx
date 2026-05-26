import { Link, useSearchParams } from 'react-router-dom'
import { format } from 'date-fns'
import { ArrowDown, ArrowLeft, ArrowUp } from 'lucide-react'
import { useRuns, useCompareRuns } from '@/hooks/use-runs'
import { useRunFeatureMetadata } from '@/hooks/use-feature-metadata'
import { FeatureImportancePanel } from '@/components/explainability/feature-importance-panel'
import { JsonBlock } from '@/components/common/json-block'
import { ErrorDisplay } from '@/components/common/error-display'
import { LoadingState } from '@/components/common/loading-state'
import { ModelFamilyBadge } from '@/components/common/model-family-badge'
import { StatusBadge } from '@/components/common/status-badge'
import { ChampionCompatibilityBadge } from '@/components/forecast-intelligence/champion-compatibility-badge'
import { getStatusVariant } from '@/lib/status-utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatNumber } from '@/lib/api'
import { ROUTES } from '@/lib/constants'
import type { ModelRun } from '@/types/api'

function fmtDate(value: string | null | undefined): string {
  return value ? format(new Date(value), 'MMM d, yyyy HH:mm') : '—'
}

/** Neutral delta indicator — sign only, no better/worse colour-coding. */
function DeltaCell({ diff }: { diff: number | null }) {
  if (diff == null) {
    return <span className="text-muted-foreground">—</span>
  }
  if (diff > 0) {
    return (
      <span className="inline-flex items-center gap-1">
        <ArrowUp className="h-3 w-3" />
        {formatNumber(diff, 4)}
      </span>
    )
  }
  if (diff < 0) {
    return (
      <span className="inline-flex items-center gap-1">
        <ArrowDown className="h-3 w-3" />
        {formatNumber(diff, 4)}
      </span>
    )
  }
  return <span>{formatNumber(diff, 4)}</span>
}

function RunPicker({
  label,
  value,
  runs,
  onSelect,
}: {
  label: string
  value: string
  runs: ModelRun[]
  onSelect: (runId: string) => void
}) {
  return (
    <div className="space-y-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <Select value={value || undefined} onValueChange={onSelect}>
        <SelectTrigger className="w-full">
          <SelectValue placeholder="Select a run…" />
        </SelectTrigger>
        <SelectContent>
          {runs.map((run) => (
            <SelectItem key={run.run_id} value={run.run_id}>
              {run.run_id.slice(0, 8)} · {run.model_type} · {run.status}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

export default function RunComparePage() {
  const [params, setParams] = useSearchParams()
  const a = params.get('a') ?? ''
  const b = params.get('b') ?? ''

  const runsQuery = useRuns({ page: 1, pageSize: 100 })
  const compareQuery = useCompareRuns(a, b, !!a && !!b)

  // MLZOO-D / PRP-31 — feature-importance side-by-side. Cross-family pairs
  // render a muted message and DO NOT fetch (the muted muted message lives
  // in `sameFamily === false` branch; both hooks gated on `enabled: sameFamily`).
  const familyA = compareQuery.data?.run_a.model_family
  const familyB = compareQuery.data?.run_b.model_family
  const sameFamily = !!familyA && familyA === familyB && familyA !== 'baseline'
  const metaA = useRunFeatureMetadata(a, sameFamily)
  const metaB = useRunFeatureMetadata(b, sameFamily)

  function selectRun(slot: 'a' | 'b', runId: string) {
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set(slot, runId)
      return next
    })
  }

  const runs = runsQuery.data?.runs ?? []
  const comparison = compareQuery.data

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <Button asChild variant="ghost" size="sm" className="-ml-2 h-7">
          <Link to={ROUTES.EXPLORER.RUNS}>
            <ArrowLeft className="mr-1 h-4 w-4" />
            Back to Model Runs
          </Link>
        </Button>
        <h1 className="text-3xl font-bold">Compare runs</h1>
        <p className="text-sm text-muted-foreground">
          Pick two model runs to compare their configuration and metrics side by side.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Select runs</CardTitle>
          <CardDescription>
            The comparison is deep-linkable — the URL carries the two run ids.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <RunPicker label="Run A" value={a} runs={runs} onSelect={(id) => selectRun('a', id)} />
          <RunPicker label="Run B" value={b} runs={runs} onSelect={(id) => selectRun('b', id)} />
        </CardContent>
      </Card>

      {(!a || !b) && (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            Select two runs above to see the comparison.
          </CardContent>
        </Card>
      )}

      {a && b && compareQuery.error && (
        <ErrorDisplay error={compareQuery.error} onRetry={() => void compareQuery.refetch()} />
      )}

      {a && b && compareQuery.isLoading && <LoadingState message="Comparing runs..." />}

      {/* PRP-37 — Champion-compatibility verdict for the picked pair. */}
      {a && b && comparison && (
        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <CardTitle>Champion compatibility</CardTitle>
                <CardDescription>
                  Two runs are comparable iff they share grain (store + product),
                  overlapping data windows, and feature_frame_version.
                </CardDescription>
              </div>
              <ChampionCompatibilityBadge
                runA={comparison.run_a}
                runB={comparison.run_b}
              />
            </div>
          </CardHeader>
        </Card>
      )}

      {a && b && comparison && (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Profile</CardTitle>
              <CardDescription>Side-by-side registry records.</CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Field</TableHead>
                    <TableHead>Run A</TableHead>
                    <TableHead>Run B</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableRow>
                    <TableCell className="font-medium">Run ID</TableCell>
                    <TableCell className="break-all font-mono text-xs">
                      {comparison.run_a.run_id}
                    </TableCell>
                    <TableCell className="break-all font-mono text-xs">
                      {comparison.run_b.run_id}
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="font-medium">Model type</TableCell>
                    <TableCell>{comparison.run_a.model_type}</TableCell>
                    <TableCell>{comparison.run_b.model_type}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="font-medium">Family</TableCell>
                    <TableCell>
                      <ModelFamilyBadge family={comparison.run_a.model_family} />
                    </TableCell>
                    <TableCell>
                      <ModelFamilyBadge family={comparison.run_b.model_family} />
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="font-medium">Status</TableCell>
                    <TableCell>
                      <StatusBadge variant={getStatusVariant(comparison.run_a.status)}>
                        {comparison.run_a.status}
                      </StatusBadge>
                    </TableCell>
                    <TableCell>
                      <StatusBadge variant={getStatusVariant(comparison.run_b.status)}>
                        {comparison.run_b.status}
                      </StatusBadge>
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="font-medium">Data window</TableCell>
                    <TableCell className="text-xs">
                      {comparison.run_a.data_window_start} → {comparison.run_a.data_window_end}
                    </TableCell>
                    <TableCell className="text-xs">
                      {comparison.run_b.data_window_start} → {comparison.run_b.data_window_end}
                    </TableCell>
                  </TableRow>
                  {/* PRP-37 — feature frame version row.
                      Renders for every comparison; pre-PRP-35 runs surface "V1 (default)". */}
                  {(comparison.run_a.feature_frame_version !== undefined ||
                    comparison.run_b.feature_frame_version !== undefined) && (
                    <TableRow data-testid="run-compare-feature-frame-row">
                      <TableCell className="font-medium">
                        Feature frame version
                      </TableCell>
                      <TableCell className="text-xs">
                        V{comparison.run_a.feature_frame_version ?? 1}
                        {comparison.run_a.feature_frame_version === undefined ||
                        comparison.run_a.feature_frame_version === null
                          ? ' (default)'
                          : ''}
                      </TableCell>
                      <TableCell className="text-xs">
                        V{comparison.run_b.feature_frame_version ?? 1}
                        {comparison.run_b.feature_frame_version === undefined ||
                        comparison.run_b.feature_frame_version === null
                          ? ' (default)'
                          : ''}
                      </TableCell>
                    </TableRow>
                  )}
                  <TableRow>
                    <TableCell className="font-medium">Config hash</TableCell>
                    <TableCell className="break-all font-mono text-xs">
                      {comparison.run_a.config_hash}
                    </TableCell>
                    <TableCell className="break-all font-mono text-xs">
                      {comparison.run_b.config_hash}
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="font-medium">Created</TableCell>
                    <TableCell className="text-xs">{fmtDate(comparison.run_a.created_at)}</TableCell>
                    <TableCell className="text-xs">{fmtDate(comparison.run_b.created_at)}</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Config diff</CardTitle>
              <CardDescription>Keys whose values differ between the two runs.</CardDescription>
            </CardHeader>
            <CardContent>
              {Object.keys(comparison.config_diff).length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  The two runs share an identical configuration.
                </p>
              ) : (
                <JsonBlock value={comparison.config_diff} />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Metrics diff</CardTitle>
              <CardDescription>
                Δ is Run B minus Run A — sign only, not a quality judgement.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {Object.keys(comparison.metrics_diff).length === 0 ? (
                <p className="text-sm text-muted-foreground">No metrics to compare.</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Metric</TableHead>
                      <TableHead>Run A</TableHead>
                      <TableHead>Run B</TableHead>
                      <TableHead>Δ</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {Object.entries(comparison.metrics_diff).map(([metric, m]) => (
                      <TableRow key={metric}>
                        <TableCell className="font-medium">{metric}</TableCell>
                        <TableCell>{m.a != null ? formatNumber(m.a, 4) : '—'}</TableCell>
                        <TableCell>{m.b != null ? formatNumber(m.b, 4) : '—'}</TableCell>
                        <TableCell>
                          <DeltaCell diff={m.diff} />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Feature Importance (Run A vs Run B)</CardTitle>
              <CardDescription>
                Native importance / coefficients side by side. Cross-family
                comparisons are not rendered because magnitudes are not
                comparable between tree and additive models.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {sameFamily ? (
                <div className="grid gap-4 md:grid-cols-2">
                  <FeatureImportancePanel
                    data={metaA.data}
                    isLoading={metaA.isLoading}
                    error={metaA.error}
                  />
                  <FeatureImportancePanel
                    data={metaB.data}
                    isLoading={metaB.isLoading}
                    error={metaB.error}
                  />
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Feature-importance comparison is only meaningful when both
                  runs share a non-baseline model family.
                </p>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
