import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowUpDown, ChevronDown, ChevronUp, Download, ExternalLink, Package } from 'lucide-react'
import { useJobs } from '@/hooks/use-jobs'
import { useProducts } from '@/hooks/use-products'
import { useInventoryStatus } from '@/hooks/use-inventory'
import { joinDemandRows, sumWindow } from '@/lib/demand-utils'
import { TimeSeriesChart } from '@/components/charts/time-series-chart'
import { EmptyState, ErrorDisplay } from '@/components/common/error-display'
import { LoadingState } from '@/components/common/loading-state'
import { StatusBadge } from '@/components/common/status-badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { downloadCsv, toCsv, type CsvColumn } from '@/lib/csv-export'
import { formatNumber } from '@/lib/api'
import { cn } from '@/lib/utils'
import { ROUTES } from '@/lib/constants'
import type { DemandRow } from '@/types/api'

/** Lead-time presets (days) for the inventory-requirement calculation. */
const LEAD_TIME_OPTIONS = [7, 14, 30]

/** Demand-table columns the user can sort by (a subset of DemandRow keys). */
type SortKey = 'sku' | 'tomorrow' | 'nextWeek' | 'nextMonth' | 'onHand' | 'inventoryRequirement'

const csvColumns: CsvColumn<DemandRow>[] = [
  { key: 'sku', header: 'SKU' },
  { key: 'productName', header: 'Product' },
  { key: 'modelType', header: 'Model' },
  { key: 'horizon', header: 'Horizon' },
  { key: 'tomorrow', header: 'Tomorrow' },
  { key: 'nextWeek', header: 'Next week' },
  { key: 'nextMonth', header: 'Next month' },
  { key: 'onHand', header: 'On hand' },
  { key: 'onOrder', header: 'On order' },
  { key: 'inventoryRequirement', header: 'Inventory need' },
  { key: 'isStockout', header: 'Stockout' },
]

/** A labelled value pair, matching the run-detail page's Field helper. */
function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  )
}

/** A clickable, sortable demand-table header cell. */
function SortHead({
  label,
  columnKey,
  sortKey,
  sortDir,
  onSort,
  numeric = false,
}: {
  label: string
  columnKey: SortKey
  sortKey: SortKey
  sortDir: 'asc' | 'desc'
  onSort: (key: SortKey) => void
  numeric?: boolean
}) {
  const active = sortKey === columnKey
  return (
    <TableHead
      className={cn('cursor-pointer select-none', numeric && 'text-right')}
      onClick={() => onSort(columnKey)}
    >
      <span className={cn('inline-flex items-center gap-1', numeric && 'flex-row-reverse')}>
        {label}
        {active ? (
          sortDir === 'asc' ? (
            <ChevronUp className="h-3.5 w-3.5" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5" />
          )
        ) : (
          <ArrowUpDown className="h-3 w-3 text-muted-foreground/50" />
        )}
      </span>
    </TableHead>
  )
}

/** A headline metric tile for the drill-in panel. */
function MetricTile({ label, value, partial }: { label: string; value: number; partial?: boolean }) {
  return (
    <div className="rounded-lg border p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-bold">{formatNumber(value)}</p>
      {partial && (
        <StatusBadge variant="warning" className="mt-1">
          partial
        </StatusBadge>
      )}
    </div>
  )
}

export default function DemandPlannerPage() {
  const navigate = useNavigate()
  const [leadTime, setLeadTime] = useState(14)
  const [selectedJobId, setSelectedJobId] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('inventoryRequirement')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

  const jobsQuery = useJobs({ page: 1, pageSize: 50, jobType: 'predict', status: 'completed' })
  // /dimensions/products caps page_size at 100; the demo's product count fits.
  const productsQuery = useProducts({ page: 1, pageSize: 100 })
  const inventoryQuery = useInventoryStatus({})

  const rows = useMemo(
    () =>
      joinDemandRows(
        jobsQuery.data?.jobs ?? [],
        productsQuery.data?.products ?? [],
        inventoryQuery.data?.items ?? [],
        leadTime,
      ),
    [jobsQuery.data, productsQuery.data, inventoryQuery.data, leadTime],
  )

  const sortedRows = useMemo(() => {
    const copy = [...rows]
    copy.sort((a, b) => {
      const av = a[sortKey]
      const bv = b[sortKey]
      // Unknown values (null inventory) always sort last.
      if (av === null) return 1
      if (bv === null) return -1
      const cmp =
        typeof av === 'string' && typeof bv === 'string'
          ? av.localeCompare(bv)
          : Number(av) - Number(bv)
      return sortDir === 'asc' ? cmp : -cmp
    })
    return copy
  }, [rows, sortKey, sortDir])

  const isLoading = jobsQuery.isLoading || productsQuery.isLoading || inventoryQuery.isLoading
  const error = jobsQuery.error ?? productsQuery.error ?? inventoryQuery.error
  const selectedRow = rows.find((row) => row.jobId === selectedJobId)

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((dir) => (dir === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir(key === 'sku' ? 'asc' : 'desc')
    }
  }

  function handleExport() {
    downloadCsv('demand-planner.csv', toCsv(sortedRows, csvColumns))
  }

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Demand Planner</h1>
        <ErrorDisplay error={error} />
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Demand Planner</h1>
        <LoadingState message="Loading demand data..." />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Demand Planner</h1>
        <p className="text-sm text-muted-foreground">
          Every completed forecast rolled up into tomorrow / next-week / next-month demand,
          joined to current stock to show what needs reordering.
        </p>
      </div>

      {rows.length === 0 ? (
        <EmptyState
          title="No completed forecasts"
          description="Run a forecast on the Forecast page first — completed prediction jobs appear here as demand rows."
          icon={<Package className="h-12 w-12" />}
          action={{
            label: 'Go to Forecast',
            onClick: () => navigate(ROUTES.VISUALIZE.FORECAST),
          }}
        />
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle>SKU demand</CardTitle>
              <CardDescription>
                {rows.length} forecast{rows.length === 1 ? '' : 's'}. The inventory requirement
                covers demand over the selected lead time.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-muted-foreground">Lead time</span>
                  <Select
                    value={String(leadTime)}
                    onValueChange={(value) => setLeadTime(Number(value))}
                  >
                    <SelectTrigger className="w-[140px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {LEAD_TIME_OPTIONS.map((days) => (
                        <SelectItem key={days} value={String(days)}>
                          {days} days
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <Button variant="outline" size="sm" onClick={handleExport}>
                  <Download className="mr-2 h-4 w-4" />
                  Export CSV
                </Button>
              </div>

              <Table>
                <TableHeader>
                  <TableRow>
                    <SortHead
                      label="SKU"
                      columnKey="sku"
                      sortKey={sortKey}
                      sortDir={sortDir}
                      onSort={handleSort}
                    />
                    <TableHead>Product</TableHead>
                    <SortHead
                      label="Tomorrow"
                      columnKey="tomorrow"
                      sortKey={sortKey}
                      sortDir={sortDir}
                      onSort={handleSort}
                      numeric
                    />
                    <SortHead
                      label="Next week"
                      columnKey="nextWeek"
                      sortKey={sortKey}
                      sortDir={sortDir}
                      onSort={handleSort}
                      numeric
                    />
                    <SortHead
                      label="Next month"
                      columnKey="nextMonth"
                      sortKey={sortKey}
                      sortDir={sortDir}
                      onSort={handleSort}
                      numeric
                    />
                    <SortHead
                      label="On hand"
                      columnKey="onHand"
                      sortKey={sortKey}
                      sortDir={sortDir}
                      onSort={handleSort}
                      numeric
                    />
                    <SortHead
                      label="Inventory need"
                      columnKey="inventoryRequirement"
                      sortKey={sortKey}
                      sortDir={sortDir}
                      onSort={handleSort}
                      numeric
                    />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sortedRows.map((row) => (
                    <TableRow
                      key={row.jobId}
                      onClick={() => setSelectedJobId(row.jobId)}
                      className={cn(
                        'cursor-pointer',
                        row.jobId === selectedJobId && 'bg-muted',
                      )}
                    >
                      <TableCell className="font-mono text-xs">
                        <span className="inline-flex items-center gap-2">
                          {row.sku}
                          {row.isStockout && (
                            <StatusBadge variant="error">stockout</StatusBadge>
                          )}
                        </span>
                      </TableCell>
                      <TableCell>{row.productName}</TableCell>
                      <TableCell className="text-right">{formatNumber(row.tomorrow)}</TableCell>
                      <TableCell className="text-right">{formatNumber(row.nextWeek)}</TableCell>
                      <TableCell className="text-right">
                        <span className="inline-flex items-center justify-end gap-1">
                          {formatNumber(row.nextMonth)}
                          {row.nextMonthPartial && (
                            <StatusBadge variant="warning">partial</StatusBadge>
                          )}
                        </span>
                      </TableCell>
                      <TableCell className="text-right">
                        {row.onHand === null ? '—' : formatNumber(row.onHand)}
                      </TableCell>
                      <TableCell className="text-right font-medium">
                        {row.inventoryRequirement === null
                          ? '—'
                          : formatNumber(row.inventoryRequirement)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {selectedRow && (
            <Card>
              <CardHeader>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <CardTitle className="font-mono">{selectedRow.sku}</CardTitle>
                    <CardDescription>
                      {selectedRow.productName} · {selectedRow.modelType} ·{' '}
                      {selectedRow.horizon}-day horizon
                    </CardDescription>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button asChild variant="outline" size="sm">
                      <Link to={`/explorer/jobs/${selectedRow.jobId}`}>
                        <ExternalLink className="mr-2 h-4 w-4" />
                        Source job
                      </Link>
                    </Button>
                    {selectedRow.runId && (
                      <Button asChild variant="outline" size="sm">
                        <Link to={`/explorer/runs/${selectedRow.runId}`}>
                          <ExternalLink className="mr-2 h-4 w-4" />
                          Model run
                        </Link>
                      </Button>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <MetricTile label="Tomorrow" value={selectedRow.tomorrow} />
                  <MetricTile label="Next week" value={selectedRow.nextWeek} />
                  <MetricTile
                    label="Next month"
                    value={selectedRow.nextMonth}
                    partial={selectedRow.nextMonthPartial}
                  />
                </div>

                <div>
                  <h3 className="mb-2 text-sm font-medium">Reorder breakdown</h3>
                  <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                    <Field
                      label={`Lead-time demand (${leadTime}d)`}
                      value={formatNumber(sumWindow(selectedRow.forecasts, leadTime))}
                    />
                    <Field
                      label="On hand"
                      value={selectedRow.onHand === null ? 'Unknown' : formatNumber(selectedRow.onHand)}
                    />
                    <Field
                      label="On order"
                      value={
                        selectedRow.onOrder === null ? 'Unknown' : formatNumber(selectedRow.onOrder)
                      }
                    />
                    <Field
                      label="Inventory requirement"
                      value={
                        selectedRow.inventoryRequirement === null
                          ? 'Unknown — no stock data'
                          : formatNumber(selectedRow.inventoryRequirement)
                      }
                    />
                  </dl>
                </div>

                <TimeSeriesChart
                  title="Daily demand curve"
                  description={`${selectedRow.forecasts.length}-day forecast`}
                  data={selectedRow.forecasts}
                  predictedKey="forecast"
                  showActual={false}
                  showPredicted
                />
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
