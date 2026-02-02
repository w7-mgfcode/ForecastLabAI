import { useState } from 'react'
import { format } from 'date-fns'
import { ColumnDef, PaginationState } from '@tanstack/react-table'
import { useRuns } from '@/hooks/use-runs'
import { DataTable } from '@/components/data-table/data-table'
import { DataTableToolbar } from '@/components/data-table/data-table-toolbar'
import { StatusBadge } from '@/components/common/status-badge'
import { getStatusVariant } from '@/lib/status-utils'
import { ErrorDisplay } from '@/components/common/error-display'
import type { ModelRun, RunStatus } from '@/types/api'
import { DEFAULT_PAGE_SIZE } from '@/lib/constants'

const columns: ColumnDef<ModelRun>[] = [
  {
    accessorKey: 'run_id',
    header: 'Run ID',
    cell: ({ row }) => (
      <span className="font-mono text-xs">{row.original.run_id.substring(0, 8)}...</span>
    ),
  },
  {
    accessorKey: 'status',
    header: 'Status',
    cell: ({ row }) => (
      <StatusBadge variant={getStatusVariant(row.original.status)}>
        {row.original.status}
      </StatusBadge>
    ),
  },
  {
    accessorKey: 'model_type',
    header: 'Model Type',
    cell: ({ row }) => <span className="font-medium">{row.original.model_type}</span>,
  },
  {
    accessorKey: 'store_id',
    header: 'Store',
  },
  {
    accessorKey: 'product_id',
    header: 'Product',
  },
  {
    accessorKey: 'data_window_start',
    header: 'Data Window',
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
    cell: ({ row }) => {
      const mae = row.original.metrics?.mae
      return mae !== undefined ? mae.toFixed(2) : '-'
    },
  },
  {
    accessorKey: 'created_at',
    header: 'Created',
    cell: ({ row }) => format(new Date(row.original.created_at), 'MMM d, HH:mm'),
  },
]

export default function RunsExplorerPage() {
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: DEFAULT_PAGE_SIZE,
  })
  const [filters, setFilters] = useState<Record<string, string | undefined>>({})

  const { data, isLoading, error, refetch } = useRuns({
    page: pagination.pageIndex + 1,
    pageSize: pagination.pageSize,
    modelType: filters.modelType,
    status: filters.status as RunStatus | undefined,
  })

  const handleFilterChange = (key: string, value: string | undefined) => {
    setFilters((prev) => ({ ...prev, [key]: value }))
    setPagination((prev) => ({ ...prev, pageIndex: 0 }))
  }

  const handleReset = () => {
    setFilters({})
    setPagination({ pageIndex: 0, pageSize: DEFAULT_PAGE_SIZE })
  }

  const hasActiveFilters = Object.values(filters).some(Boolean)

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Model Runs</h1>
        <ErrorDisplay error={error} onRetry={refetch} />
      </div>
    )
  }

  const pageCount = data ? Math.ceil(data.total / pagination.pageSize) : 0

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Model Runs</h1>

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
        filterValues={filters}
        onFilterChange={handleFilterChange}
        onReset={handleReset}
        hasActiveFilters={hasActiveFilters}
      />

      <DataTable
        columns={columns}
        data={data?.runs ?? []}
        pageCount={pageCount}
        pagination={pagination}
        onPaginationChange={setPagination}
        isLoading={isLoading}
        emptyMessage="No model runs found."
      />
    </div>
  )
}
