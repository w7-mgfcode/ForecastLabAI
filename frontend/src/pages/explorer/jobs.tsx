import { format } from 'date-fns'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ColumnDef, OnChangeFn, PaginationState, SortingState } from '@tanstack/react-table'
import { Download, XCircle } from 'lucide-react'
import { useJobs, useCancelJob } from '@/hooks/use-jobs'
import { DataTable } from '@/components/data-table/data-table'
import { DataTableToolbar } from '@/components/data-table/data-table-toolbar'
import { DataTableColumnHeader } from '@/components/data-table/data-table-column-header'
import { StatusBadge } from '@/components/common/status-badge'
import { getStatusVariant } from '@/lib/status-utils'
import { ErrorDisplay } from '@/components/common/error-display'
import { Button } from '@/components/ui/button'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { toast } from 'sonner'
import { toCsv, downloadCsv, type CsvColumn } from '@/lib/csv-export'
import type { Job, JobStatus, JobType } from '@/types/api'
import { DEFAULT_PAGE_SIZE } from '@/lib/constants'

const csvColumns: CsvColumn<Job>[] = [
  { key: 'job_id', header: 'Job ID' },
  { key: 'job_type', header: 'Type' },
  { key: 'status', header: 'Status' },
  { key: 'run_id', header: 'Run ID' },
  { key: 'created_at', header: 'Created' },
  { key: 'completed_at', header: 'Completed' },
]

export default function JobsMonitorPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  // URL query string is the single source of truth for filter/sort/page state,
  // so a pasted URL reproduces the exact view.
  const jobType = searchParams.get('job_type') ?? undefined
  const status = searchParams.get('status') ?? undefined
  const page = Number(searchParams.get('page')) || 1
  const sortBy = searchParams.get('sort_by') ?? undefined
  const sortOrder: 'asc' | 'desc' = searchParams.get('sort_order') === 'desc' ? 'desc' : 'asc'

  const pagination: PaginationState = {
    pageIndex: page - 1,
    pageSize: DEFAULT_PAGE_SIZE,
  }
  const sorting: SortingState = sortBy ? [{ id: sortBy, desc: sortOrder === 'desc' }] : []

  const { data, isLoading, error, refetch } = useJobs({
    page,
    pageSize: pagination.pageSize,
    jobType: jobType as JobType | undefined,
    status: status as JobStatus | undefined,
    sortBy,
    sortOrder: sortBy ? sortOrder : undefined,
  })

  const cancelJob = useCancelJob()

  const handleCancelJob = async (jobId: string) => {
    // mutateAsync rejects on failure — catch it so a cancel error surfaces as
    // a toast instead of an unhandled promise rejection.
    try {
      await cancelJob.mutateAsync(jobId)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to cancel job')
    }
  }

  const columns: ColumnDef<Job>[] = [
    {
      accessorKey: 'job_id',
      header: 'Job ID',
      enableSorting: false,
      enableHiding: false,
      cell: ({ row }) => (
        <span className="font-mono text-xs">{row.original.job_id.substring(0, 8)}...</span>
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
      accessorKey: 'job_type',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Type" />,
      cell: ({ row }) => (
        <span className="capitalize font-medium">{row.original.job_type}</span>
      ),
    },
    {
      accessorKey: 'params',
      header: 'Model',
      enableSorting: false,
      cell: ({ row }) => {
        const modelType = row.original.params?.model_type
        return modelType ? String(modelType) : '-'
      },
    },
    {
      accessorKey: 'created_at',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Created" />,
      cell: ({ row }) => format(new Date(row.original.created_at), 'MMM d, HH:mm'),
    },
    {
      accessorKey: 'completed_at',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Completed" />,
      cell: ({ row }) =>
        row.original.completed_at
          ? format(new Date(row.original.completed_at), 'MMM d, HH:mm')
          : '-',
    },
    {
      id: 'actions',
      header: '',
      enableSorting: false,
      enableHiding: false,
      cell: ({ row }) => {
        const job = row.original
        if (job.status !== 'pending') return null

        return (
          // The row is clickable (onRowClick navigates) — stop the cancel
          // control's clicks from bubbling up and also triggering navigation.
          <div onClick={(e) => e.stopPropagation()}>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="ghost" size="icon-sm">
                  <XCircle className="h-4 w-4 text-destructive" />
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Cancel Job</AlertDialogTitle>
                  <AlertDialogDescription>
                    Are you sure you want to cancel this job? This action cannot be undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>No, keep it</AlertDialogCancel>
                  <AlertDialogAction onClick={() => handleCancelJob(job.job_id)}>
                    Yes, cancel
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        )
      },
    },
  ]

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
    const paramKey = key === 'jobType' ? 'job_type' : key
    updateParams({ [paramKey]: value, page: '1' })
  }

  const handleReset = () => {
    setSearchParams(new URLSearchParams())
  }

  const handleExport = () => {
    downloadCsv('jobs.csv', toCsv(data?.jobs ?? [], csvColumns))
  }

  const hasActiveFilters = !!jobType || !!status || !!sortBy

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Jobs</h1>
        <ErrorDisplay error={error} onRetry={() => void refetch()} />
      </div>
    )
  }

  const pageCount = data ? Math.ceil(data.total / pagination.pageSize) : 0

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Jobs Monitor</h1>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <DataTableToolbar
          filters={[
            {
              key: 'jobType',
              label: 'Type',
              options: [
                { label: 'Train', value: 'train' },
                { label: 'Predict', value: 'predict' },
                { label: 'Backtest', value: 'backtest' },
              ],
            },
            {
              key: 'status',
              label: 'Status',
              options: [
                { label: 'Pending', value: 'pending' },
                { label: 'Running', value: 'running' },
                { label: 'Completed', value: 'completed' },
                { label: 'Failed', value: 'failed' },
                { label: 'Cancelled', value: 'cancelled' },
              ],
            },
          ]}
          filterValues={{ jobType, status }}
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
        data={data?.jobs ?? []}
        pageCount={pageCount}
        pagination={pagination}
        onPaginationChange={handlePaginationChange}
        sorting={sorting}
        onSortingChange={handleSortingChange}
        onRowClick={(job) => navigate(`/explorer/jobs/${job.job_id}`)}
        enableColumnVisibility
        isLoading={isLoading}
        emptyMessage="No jobs found."
      />
    </div>
  )
}
