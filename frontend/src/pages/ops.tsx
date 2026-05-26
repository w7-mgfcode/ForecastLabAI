import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Activity, AlertTriangle, CheckCircle2, Clock, Download, RefreshCw } from 'lucide-react'
import { toast } from 'sonner'
import { useModelHealth, useOpsSummary, useRetrainingCandidates } from '@/hooks/use-ops'
import { useProviderHealth } from '@/hooks/use-config'
import { useCreateJob } from '@/hooks/use-jobs'
import { useCreateAlias, useRun, useAliases } from '@/hooks/use-runs'
import { PromoteConfirmationDialog } from '@/components/forecast-intelligence/promote-confirmation-dialog'
import {
  attentionBadgeVariant,
  attentionItemLink,
  driftBadgeVariant,
  formatStaleness,
  formatWapeDelta,
  sortRetrainingCandidates,
  summaryHealthVariant,
} from '@/lib/ops-utils'
import { getStatusVariant } from '@/lib/status-utils'
import { KPICard } from '@/components/charts/kpi-card'
import { EmptyState, ErrorDisplay } from '@/components/common/error-display'
import { LoadingState } from '@/components/common/loading-state'
import { StatusBadge } from '@/components/common/status-badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Checkbox } from '@/components/ui/checkbox'
import { downloadCsv, toCsv } from '@/lib/csv-export'
import { attentionCsvColumns, buildIncidentMarkdown, downloadMarkdown } from '@/lib/incident-report'
import { buildRetrainJob } from '@/lib/ops-actions'
import { api, formatPercent, getErrorMessage } from '@/lib/api'
import { ROUTES } from '@/lib/constants'
import type { ModelRun } from '@/types/api'

/** The run + grain a "Promote to alias" dialog is currently targeting. */
interface PromoteTarget {
  runId: string
  storeId: number
  productId: number
}

/** Format an ISO timestamp / date string for display; '—' when null. */
function formatWhen(value: string | null): string {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

/** A labelled health row inside the System Health card. */
function HealthRow({ label, ok, detail }: { label: string; ok: boolean; detail?: string }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="flex items-center gap-2">
        {detail && <span className="text-xs text-muted-foreground">{detail}</span>}
        <StatusBadge variant={ok ? 'success' : 'error'}>{ok ? 'ok' : 'down'}</StatusBadge>
      </span>
    </div>
  )
}

/** A labelled value pair for the Data Freshness card. */
function FreshnessRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-sm font-medium">{value}</span>
    </div>
  )
}

export default function OpsPage() {
  const navigate = useNavigate()
  const summaryQuery = useOpsSummary()
  const candidatesQuery = useRetrainingCandidates()
  const modelHealthQuery = useModelHealth()
  const providerQuery = useProviderHealth()
  const aliasesQuery = useAliases()
  const createJob = useCreateJob()
  const createAlias = useCreateAlias()
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [retrainConfirmOpen, setRetrainConfirmOpen] = useState(false)
  const [actionBusy, setActionBusy] = useState(false)
  const [promoteTarget, setPromoteTarget] = useState<PromoteTarget | null>(null)

  // PRP-37 — load the candidate run + the current champion's run (when a
  // production alias points at this grain) for the safer Promote dialog.
  const promoteRunQuery = useRun(
    promoteTarget?.runId ?? '',
    promoteTarget !== null,
  )
  const aliasList = aliasesQuery.data ?? []
  const championAlias = promoteTarget
    ? aliasList.find(
        (a) =>
          (a.alias_name === 'production' || a.alias_name === 'champion') &&
          a.run_id !== promoteTarget.runId,
      )
    : undefined
  const championRunQuery = useRun(
    championAlias?.run_id ?? '',
    !!championAlias?.run_id,
  )

  if (summaryQuery.error) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Control Center</h1>
        <ErrorDisplay error={summaryQuery.error} onRetry={() => void summaryQuery.refetch()} />
      </div>
    )
  }

  if (summaryQuery.isLoading || !summaryQuery.data) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Control Center</h1>
        <LoadingState message="Loading operational state..." />
      </div>
    )
  }

  const summary = summaryQuery.data
  const providers = providerQuery.data ?? []
  const totalJobs = summary.jobs.counts.reduce((sum, c) => sum + c.count, 0)
  const totalRuns = summary.runs.counts.reduce((sum, c) => sum + c.count, 0)
  const staleAliases = summary.aliases.filter((a) => a.is_stale).length
  const candidates = sortRetrainingCandidates(candidatesQuery.data?.candidates ?? [])
  const modelHealthEntries = modelHealthQuery.data?.entries ?? []

  /** Download the needs-attention list as a CSV, built client-side. */
  function handleExportCsv() {
    downloadCsv('ops-attention-items.csv', toCsv(summary.attention_items, attentionCsvColumns))
  }

  /** Download the full operational snapshot as a Markdown incident report. */
  function handleExportMarkdown() {
    downloadMarkdown(
      'ops-incident-report.md',
      buildIncidentMarkdown(summary, candidates, modelHealthEntries),
    )
  }

  /** Stable selection key for a (store, product) grain. */
  const grainKey = (storeId: number, productId: number) => `${storeId}-${productId}`

  /** Toggle one grain in the bulk-retrain selection set. */
  function toggleSelected(key: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
  }

  // Selected candidates that carry a source run — the bulk-retrain work list.
  const selectedCandidates = candidates.filter(
    (candidate) =>
      selected.has(grainKey(candidate.store_id, candidate.product_id)) &&
      candidate.latest_run_id !== null,
  )

  /**
   * Bulk-retrain every selected grain. POST /jobs runs synchronously
   * server-side, so jobs are fired SEQUENTIALLY (never Promise.all) with a
   * per-item toast; the action layer reuses the existing /jobs endpoint.
   */
  async function runBulkRetrain() {
    setRetrainConfirmOpen(false)
    setActionBusy(true)
    let succeeded = 0
    let failed = 0
    for (const candidate of selectedCandidates) {
      const runId = candidate.latest_run_id
      if (runId === null) continue
      const where = `store ${candidate.store_id} / product ${candidate.product_id}`
      try {
        const run = await api<ModelRun>(`/registry/runs/${runId}`)
        await createJob.mutateAsync(buildRetrainJob(run, summary.freshness.latest_sales_date))
        succeeded += 1
        toast.success(`Retrain queued — ${where}`)
      } catch (error) {
        failed += 1
        toast.error(`Retrain failed — ${where}: ${getErrorMessage(error)}`)
      }
    }
    setSelected(new Set())
    setActionBusy(false)
    toast.message(`Bulk retrain complete — ${succeeded} queued, ${failed} failed`)
  }

  /** Open the promote-to-alias dialog for a grain's latest successful run. */
  function openPromote(runId: string | null, storeId: number, productId: number) {
    if (runId === null) return
    setPromoteTarget({ runId, storeId, productId })
  }

  /** Promote the targeted run to a deployment alias via POST /registry/aliases. */
  async function runPromote(aliasName: string) {
    if (promoteTarget === null) return
    const target = promoteTarget
    const name = aliasName.trim()
    setActionBusy(true)
    try {
      await createAlias.mutateAsync({ alias_name: name, run_id: target.runId })
      toast.success(`Promoted run to alias '${name}'`)
    } catch (error) {
      toast.error(`Promote failed: ${getErrorMessage(error)}`)
    }
    setActionBusy(false)
    setPromoteTarget(null)
  }

  /** PRP-36 enum → human-readable reason chip label. */
  function staleReasonLabel(reason: string | null): string {
    if (reason === null) return '—'
    if (reason === 'feature_frame_version_mismatch') return 'V mismatch'
    if (reason === 'newer_success_run') return 'newer success run'
    if (reason === 'artifact_not_verified') return 'artifact not verified'
    if (reason === 'run_not_success') return 'run not success'
    return reason
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Control Center</h1>
          <p className="text-sm text-muted-foreground">
            One operational view across jobs, model runs, deployment aliases, and data
            freshness — surfacing what needs attention before it affects decisions.
          </p>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm">
              <Download className="mr-2 h-4 w-4" />
              Export report
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={handleExportCsv}>CSV — attention items</DropdownMenuItem>
            <DropdownMenuItem onClick={handleExportMarkdown}>
              Markdown — full report
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {totalJobs === 0 && totalRuns === 0 ? (
        <EmptyState
          title="No operational data yet"
          description="Run the end-to-end pipeline to populate jobs and model runs — the Control Center then shows live operational state."
          icon={<Activity className="h-12 w-12" />}
          action={{ label: 'Go to Showcase', onClick: () => navigate(ROUTES.SHOWCASE) }}
        />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* Section 1 — System Health */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between gap-3">
                  <CardTitle>System Health</CardTitle>
                  <StatusBadge variant={summaryHealthVariant(summary.system)}>
                    {summaryHealthVariant(summary.system) === 'success' ? 'healthy' : 'degraded'}
                  </StatusBadge>
                </div>
                <CardDescription>API, database, and embedding-provider reachability.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="divide-y">
                  <HealthRow label="API" ok={summary.system.api_ok} />
                  <HealthRow label="Database" ok={summary.system.database_connected} />
                  {providers.map((p) => (
                    <HealthRow
                      key={p.provider}
                      label={`Provider · ${p.provider}`}
                      ok={p.reachable}
                    />
                  ))}
                </div>
                <div className="mt-3 border-t pt-3 text-sm">
                  <span className="text-muted-foreground">Latest successful job: </span>
                  <span className="font-medium">
                    {formatWhen(summary.system.latest_successful_job_at)}
                  </span>
                </div>
                <div className="mt-3 space-y-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="mr-1 text-xs text-muted-foreground">Jobs</span>
                    {summary.jobs.counts.map((c) => (
                      <StatusBadge key={c.status} variant={getStatusVariant(c.status)}>
                        {c.status} {c.count}
                      </StatusBadge>
                    ))}
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="mr-1 text-xs text-muted-foreground">Runs</span>
                    {summary.runs.counts.map((c) => (
                      <StatusBadge key={c.status} variant={getStatusVariant(c.status)}>
                        {c.status} {c.count}
                      </StatusBadge>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Section 3 — Data Freshness */}
            <Card>
              <CardHeader>
                <CardTitle>Data Freshness</CardTitle>
                <CardDescription>How current the data and model state are.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="divide-y">
                  <FreshnessRow
                    label="Latest sales date"
                    value={summary.freshness.latest_sales_date ?? '—'}
                  />
                  <FreshnessRow
                    label="Latest completed job"
                    value={formatWhen(summary.freshness.latest_job_completed_at)}
                  />
                  <FreshnessRow
                    label="Latest successful run"
                    value={formatWhen(summary.freshness.latest_run_completed_at)}
                  />
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Section 2 — KPI row */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <KPICard
              title="Active Jobs"
              value={summary.jobs.active_total}
              description={`${summary.jobs.completed_today} completed today`}
              icon={Activity}
            />
            <KPICard
              title="Failed Jobs"
              value={summary.jobs.failed_total}
              description={`of ${totalJobs} total`}
              icon={AlertTriangle}
            />
            <KPICard
              title="Run Success Rate"
              value={
                summary.runs.success_rate === null
                  ? '—'
                  : formatPercent(summary.runs.success_rate * 100)
              }
              description={`${totalRuns} runs · ${summary.runs.failed_total} failed`}
              icon={CheckCircle2}
            />
            <KPICard
              title="Stale Aliases"
              value={staleAliases}
              description={`of ${summary.aliases.length} aliases`}
              icon={Clock}
            />
          </div>

          {/* Section 4 — Needs Attention */}
          <Card>
            <CardHeader>
              <CardTitle>Needs Attention</CardTitle>
              <CardDescription>
                Recent failed jobs, failed runs, and stale deployment aliases. Each row links
                to its Explorer detail page.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {summary.attention_items.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  Nothing needs attention — no failed jobs, failed runs, or stale aliases.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Type</TableHead>
                      <TableHead>Item</TableHead>
                      <TableHead>Detail</TableHead>
                      <TableHead>When</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {summary.attention_items.map((item) => (
                      <TableRow key={`${item.item_type}-${item.entity_id}`}>
                        <TableCell>
                          <StatusBadge variant={attentionBadgeVariant(item.item_type)}>
                            {item.item_type.replace('_', ' ')}
                          </StatusBadge>
                        </TableCell>
                        <TableCell>
                          <Link
                            to={attentionItemLink(item)}
                            className="font-medium text-primary hover:underline"
                          >
                            {item.label}
                          </Link>
                        </TableCell>
                        <TableCell className="max-w-md truncate text-sm text-muted-foreground">
                          {item.detail}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {formatWhen(item.occurred_at)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          {/* PRP-37 — Stale aliases. Surfaces the new
              feature_frame_version_mismatch reason chip (PRP-36) alongside
              the existing newer-run / artifact-not-verified / run-not-success
              reasons. */}
          {summary.aliases.some((a) => a.is_stale) && (
            <Card>
              <CardHeader>
                <CardTitle>Stale aliases</CardTitle>
                <CardDescription>
                  Deployment aliases the Control Center flagged as out of date.
                  Each row carries the precise stale reason and (when known)
                  the alias vs. comparable run's feature_frame_version.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Alias</TableHead>
                      <TableHead>Grain</TableHead>
                      <TableHead>Reason</TableHead>
                      <TableHead>Alias V</TableHead>
                      <TableHead>Comparable V</TableHead>
                      <TableHead className="text-right">WAPE</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {summary.aliases
                      .filter((a) => a.is_stale)
                      .map((alias) => (
                        <TableRow
                          key={`${alias.alias_name}-${alias.run_id}`}
                          data-testid={`stale-alias-row-${alias.alias_name}`}
                        >
                          <TableCell className="font-medium">
                            {alias.alias_name}
                          </TableCell>
                          <TableCell className="font-mono text-xs">
                            store {alias.store_id} / product{' '}
                            {alias.product_id}
                          </TableCell>
                          <TableCell>
                            <StatusBadge
                              variant={
                                alias.stale_reason ===
                                'feature_frame_version_mismatch'
                                  ? 'warning'
                                  : 'info'
                              }
                              data-testid={`stale-reason-${alias.alias_name}`}
                            >
                              {staleReasonLabel(alias.stale_reason)}
                            </StatusBadge>
                          </TableCell>
                          <TableCell className="font-mono text-xs">
                            {alias.alias_feature_frame_version
                              ? `V${alias.alias_feature_frame_version}`
                              : '—'}
                          </TableCell>
                          <TableCell className="font-mono text-xs">
                            {alias.comparable_run_feature_frame_version
                              ? `V${alias.comparable_run_feature_frame_version}`
                              : '—'}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {alias.wape === null ? '—' : alias.wape.toFixed(1)}
                          </TableCell>
                        </TableRow>
                      ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}

          {/* Section 5 — Model Health */}
          <Card>
            <CardHeader>
              <CardTitle>Model Health</CardTitle>
              <CardDescription>
                Forecast-error (WAPE) drift per store / product, classified from each grain's
                successful-run history. Degrading grains are listed first.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {modelHealthQuery.isLoading ? (
                <LoadingState message="Loading model health..." />
              ) : modelHealthEntries.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  No model health to evaluate — no successful model runs yet.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Store</TableHead>
                      <TableHead>Product</TableHead>
                      <TableHead>Drift</TableHead>
                      <TableHead className="text-right">Latest WAPE</TableHead>
                      <TableHead className="text-right">Prev WAPE</TableHead>
                      <TableHead className="text-right">Δ WAPE</TableHead>
                      <TableHead className="text-right">Runs evaluated</TableHead>
                      <TableHead className="text-right">Staleness</TableHead>
                      <TableHead className="text-right">Action</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {modelHealthEntries.map((entry) => (
                      <TableRow
                        key={`${entry.store_id}-${entry.product_id}`}
                        data-testid={`model-health-row-${entry.store_id}-${entry.product_id}`}
                      >
                        <TableCell className="font-mono text-xs">{entry.store_id}</TableCell>
                        <TableCell className="font-mono text-xs">{entry.product_id}</TableCell>
                        <TableCell>
                          <StatusBadge variant={driftBadgeVariant(entry.drift_direction)}>
                            {entry.drift_direction}
                          </StatusBadge>
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {entry.latest_wape === null ? '—' : entry.latest_wape.toFixed(1)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {entry.previous_wape === null
                            ? '—'
                            : entry.previous_wape.toFixed(1)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {formatWapeDelta(entry.wape_delta)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {entry.run_count}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {formatStaleness(entry.staleness_days)}
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={entry.latest_run_id === null || actionBusy}
                            onClick={() =>
                              openPromote(entry.latest_run_id, entry.store_id, entry.product_id)
                            }
                          >
                            Promote
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          {/* Section 6 — Retraining Queue */}
          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <CardTitle>Retraining Queue</CardTitle>
                  <CardDescription>
                    Store / product pairs ranked by a retraining-priority score that blends
                    staleness with forecast error (WAPE). Select rows to retrain in bulk.
                  </CardDescription>
                </div>
                <Button
                  size="sm"
                  disabled={selectedCandidates.length === 0 || actionBusy}
                  onClick={() => setRetrainConfirmOpen(true)}
                >
                  <RefreshCw className="mr-2 h-4 w-4" />
                  Retrain selected ({selectedCandidates.length})
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {candidatesQuery.isLoading ? (
                <LoadingState message="Loading retraining candidates..." />
              ) : candidates.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  No retraining candidates — no successful model runs to evaluate yet.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-10">
                        <span className="sr-only">Select</span>
                      </TableHead>
                      <TableHead>Store</TableHead>
                      <TableHead>Product</TableHead>
                      <TableHead className="text-right">Priority</TableHead>
                      <TableHead className="text-right">Staleness</TableHead>
                      <TableHead className="text-right">WAPE</TableHead>
                      <TableHead>Reason</TableHead>
                      <TableHead className="text-right">Action</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {candidates.map((candidate) => {
                      const key = grainKey(candidate.store_id, candidate.product_id)
                      return (
                        <TableRow key={key}>
                          <TableCell>
                            <Checkbox
                              checked={selected.has(key)}
                              disabled={candidate.latest_run_id === null}
                              onCheckedChange={() => toggleSelected(key)}
                              aria-label={`Select store ${candidate.store_id} product ${candidate.product_id}`}
                            />
                          </TableCell>
                          <TableCell className="font-mono text-xs">
                            {candidate.store_id}
                          </TableCell>
                          <TableCell className="font-mono text-xs">
                            {candidate.product_id}
                          </TableCell>
                          <TableCell className="text-right font-medium tabular-nums">
                            {candidate.priority_score.toFixed(2)}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {formatStaleness(candidate.staleness_days)}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {candidate.wape === null ? '—' : candidate.wape.toFixed(1)}
                          </TableCell>
                          <TableCell className="text-sm text-muted-foreground">
                            {candidate.reason}
                          </TableCell>
                          <TableCell className="text-right">
                            <Button
                              variant="outline"
                              size="sm"
                              disabled={candidate.latest_run_id === null || actionBusy}
                              onClick={() =>
                                openPromote(
                                  candidate.latest_run_id,
                                  candidate.store_id,
                                  candidate.product_id,
                                )
                              }
                            >
                              Promote
                            </Button>
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {/* Confirm gate — bulk retrain of the selected grains. */}
      <AlertDialog open={retrainConfirmOpen} onOpenChange={setRetrainConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Retrain {selectedCandidates.length} grain
              {selectedCandidates.length === 1 ? '' : 's'}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              This creates one training job per selected store / product via the existing
              POST /jobs endpoint. Jobs run sequentially and each may take a moment; the
              outcome of every job is reported individually.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => void runBulkRetrain()}>Retrain</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* PRP-37 — safer Promote dialog: artifact verify + worse-WAPE +
          V-mismatch gates. Replaces the prior inline alias-name AlertDialog. */}
      {promoteTarget && promoteRunQuery.data && (
        <PromoteConfirmationDialog
          open
          onOpenChange={(open) => {
            if (!open) setPromoteTarget(null)
          }}
          run={promoteRunQuery.data}
          currentChampion={championRunQuery.data}
          defaultAliasName="production"
          onConfirm={runPromote}
          isPromoting={actionBusy}
        />
      )}
    </div>
  )
}
