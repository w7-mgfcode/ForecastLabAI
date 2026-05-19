import { useNavigate, Link } from 'react-router-dom'
import { Activity, AlertTriangle, CheckCircle2, Clock } from 'lucide-react'
import { useOpsSummary, useRetrainingCandidates } from '@/hooks/use-ops'
import { useProviderHealth } from '@/hooks/use-config'
import {
  attentionBadgeVariant,
  attentionItemLink,
  formatStaleness,
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
import { formatPercent } from '@/lib/api'
import { ROUTES } from '@/lib/constants'

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
  const providerQuery = useProviderHealth()

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

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Control Center</h1>
        <p className="text-sm text-muted-foreground">
          One operational view across jobs, model runs, deployment aliases, and data
          freshness — surfacing what needs attention before it affects decisions.
        </p>
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

          {/* Section 5 — Retraining Queue */}
          <Card>
            <CardHeader>
              <CardTitle>Retraining Queue</CardTitle>
              <CardDescription>
                Store / product pairs ranked by a retraining-priority score that blends
                staleness with forecast error (WAPE).
              </CardDescription>
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
                      <TableHead>Store</TableHead>
                      <TableHead>Product</TableHead>
                      <TableHead className="text-right">Priority</TableHead>
                      <TableHead className="text-right">Staleness</TableHead>
                      <TableHead className="text-right">WAPE</TableHead>
                      <TableHead>Reason</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {candidates.map((c) => (
                      <TableRow key={`${c.store_id}-${c.product_id}`}>
                        <TableCell className="font-mono text-xs">{c.store_id}</TableCell>
                        <TableCell className="font-mono text-xs">{c.product_id}</TableCell>
                        <TableCell className="text-right font-medium tabular-nums">
                          {c.priority_score.toFixed(2)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {formatStaleness(c.staleness_days)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {c.wape === null ? '—' : c.wape.toFixed(1)}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {c.reason}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
