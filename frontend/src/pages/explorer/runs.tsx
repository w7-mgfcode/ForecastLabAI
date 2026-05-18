import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { format } from 'date-fns'
import { ColumnDef, OnChangeFn, PaginationState, SortingState } from '@tanstack/react-table'
import { Download, GitCompare } from 'lucide-react'
import { useRuns } from '@/hooks/use-runs'
import { DataTable } from '@/components/data-table/data-table'
import { DataTableToolbar } from '@/components/data-table/data-table-toolbar'
import { DataTableColumnHeader } from '@/components/data-table/data-table-column-header'
import { StatusBadge } from '@/components/common/status-badge'
import { getStatusVariant } from '@/lib/status-utils'
import { ErrorDisplay } from '@/components/common/error-display'
import { Button } from '@/components/ui/button'
import { toCsv, downloadCsv, type CsvColumn } from '@/lib/csv-export'
import type { ModelRun, RunStatus } from '@/types/api'
import { DEFAULT_PAGE_SIZE, ROUTES } from '@/lib/constants'

const columns: ColumnDef<ModelRun>[] = [
  {
    accessorKey: 'run_id',
    header: 'Run ID',
    enableSorting: false,
    enableHiding: false,
    cell: ({ row }) => (
      <span className="font-mono text-xs">{row.original.run_id.substring(0, 8)}...</span>
    ),
  },
  {
    accessorKey: 'status',
    header: ({ column }) => <DataTableColumnHeader column={column} title="Status" />,
    cell: ({ row }) => (
      <StatusBadge variant={getStatusVariant(row.original.status)}>
        {row.original.status}
      </StatusBadge>
    ),
  },
  {
    accessorKey: 'model_type',
    header: ({ column }) => <DataTableColumnHeader column={column} title="Model Type" />,
    cell: ({ row }) => <span className="font-medium">{row.original.model_type}</span>,
  },
  {
    accessorKey: 'store_id',
    header: ({ column }) => <DataTableColumnHeader column={column} title="Store" />,
  },
  {
    accessorKey: 'product_id',
    header: ({ column }) => <DataTableColumnHeader column={column} title="Product" />,
  },
  {
    accessorKey: 'data_window_start',
    header: 'Data Window',
    enableSorting: false,
    cell: ({ row }) => (
      <span className="text-xs">
        {format(new Date(row.original.data_window_start), 'MMM d')} -{' '}
        {format(new Date(row.original.data_window_end), 'MMM d, yyyy')}
      </span>
    ),
  },
  {
    accessorKey: 'metrics',
    header: 'MAE',
    enableSorting: false,
    cell: ({ row }) => {
      const mae = row.original.metrics?.mae
      return mae !== undefined ? mae.toFixed(2) : '-'
    },
  },
  {
    accessorKey: 'created_at',
    header: ({ column }) => <DataTableColumnHeader column={column} title="Created" />,
    cell: ({ row }) => format(new Date(row.original.created_at), 'MMM d, HH:mm'),
  },
]

const csvColumns: CsvColumn<ModelRun>[] = [
  { key: 'run_id', header: 'Run ID' },
  { key: 'status', header: 'Status' },
  { key: 'model_type', header: 'Model Type' },
  { key: 'store_id', header: 'Store' },
  { key: 'product_id', header: 'Product' },
  { key: 'data_window_start', header: 'Data Window Start' },
  { key: 'data_window_end', header: 'Data Window End' },
  { key: 'created_at', header: 'Created' },
]

export default function RunsExplorerPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  // URL query string is the single source of truth for filter/sort/page state,
  // so a pasted URL reproduces the exact view.
  const modelType = searchParams.get('model_type') ?? undefined
  const status = searchParams.get('status') ?? undefined
  const page = Number(searchParams.get('page')) || 1
  const sortBy = searchParams.get('sort_by') ?? undefined
  const sortOrder: 'asc' | 'desc' = searchParams.get('sort_order') === 'desc' ? 'desc' : 'asc'

  const pagination: PaginationState = {
    pageIndex: page - 1,
    pageSize: DEFAULT_PAGE_SIZE,
  }
  const sorting: SortingState = sortBy ? [{ id: sortBy, desc: sortOrder === 'desc' }] : []

  const { data, isLoading, error, refetch } = useRuns({
    page,
    pageSize: pagination.pageSize,
    modelType,
    status: status as RunStatus | undefined,
    sortBy,
    sortOrder: sortBy ? sortOrder : undefined,
  })

  function updateParams(updates: Record<string, string | undefined>) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      for (const [key, value] of Object.entries(updates)) {
        if (value === undefined || value === '') next.delete(key)
        else next.set(key, value)
      }
      return next
    })
  }

  const handlePaginationChange: OnChangeFn<PaginationState> = (updater) => {
    const next = typeof updater === 'function' ? updater(pagination) : updater
    updateParams({ page: String(next.pageIndex + 1) })
  }

  const handleSortingChange: OnChangeFn<SortingState> = (updater) => {
    const next = typeof updater === 'function' ? updater(sorting) : updater
    const first = next[0]
    updateParams({
      sort_by: first?.id,
      sort_order: first ? (first.desc ? 'desc' : 'asc') : undefined,
      page: '1',
    })
  }

  const handleFilterChange = (key: string, value: string | undefined) => {
    const paramKey = key === 'modelType' ? 'model_type' : key
    updateParams({ [paramKey]: value, page: '1' })
  }

  const handleReset = () => {
    setSearchParams(new URLSearchParams())
  }

  const handleExport = () => {
    downloadCsv('model-runs.csv', toCsv(data?.runs ?? [], csvColumns))
  }

  const hasActiveFilters = !!modelType || !!status || !!sortBy

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Model Runs</h1>
        <ErrorDisplay error={error} onRetry={() => void refetch()} />
      </div>
    )
  }

  const pageCount = data ? Math.ceil(data.total / pagination.pageSize) : 0

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-3xl font-bold">Model Runs</h1>
        <Button asChild variant="outline" size="sm" className="h-8">
          <Link to={ROUTES.EXPLORER.RUN_COMPARE}>
            <GitCompare className="mr-2 h-4 w-4" />
            Compare runs
          </Link>
        </Button>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <DataTableToolbar
          filters={[
            {
              key: 'modelType',
              label: 'Model',
              options: [
                { label: 'Naive', value: 'naive' },
                { label: 'Seasonal Naive', value: 'seasonal_naive' },
                { label: 'Moving Average', value: 'moving_average' },
                { label: 'LightGBM', value: 'lightgbm' },
              ],
            },
            {
              key: 'status',
              label: 'Status',
              options: [
                { label: 'Pending', value: 'pending' },
                { label: 'Running', value: 'running' },
                { label: 'Success', value: 'success' },
                { label: 'Failed', value: 'failed' },
                { label: 'Archived', value: 'archived' },
              ],
            },
          ]}
          filterValues={{ modelType, status }}
          onFilterChange={handleFilterChange}
          onReset={handleReset}
          hasActiveFilters={hasActiveFilters}
        />
        <Button variant="outline" size="sm" className="h-8" onClick={handleExport}>
          <Download className="mr-2 h-4 w-4" />
          Export CSV
        </Button>
      </div>

      <DataTable
        columns={columns}
        data={data?.runs ?? []}
        pageCount={pageCount}
        pagination={pagination}
        onPaginationChange={handlePaginationChange}
        sorting={sorting}
        onSortingChange={handleSortingChange}
        onRowClick={(run) => navigate(`/explorer/runs/${run.run_id}`)}
        enableColumnVisibility
        isLoading={isLoading}
        emptyMessage="No model runs found."
      />
    </div>
  )
}
