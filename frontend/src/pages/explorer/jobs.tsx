import { useState } from 'react'
import { format } from 'date-fns'
import { ColumnDef, PaginationState } from '@tanstack/react-table'
import { XCircle } from 'lucide-react'
import { useJobs, useCancelJob } from '@/hooks/use-jobs'
import { DataTable } from '@/components/data-table/data-table'
import { DataTableToolbar } from '@/components/data-table/data-table-toolbar'
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
import type { Job, JobStatus, JobType } from '@/types/api'
import { DEFAULT_PAGE_SIZE } from '@/lib/constants'

export default function JobsMonitorPage() {
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: DEFAULT_PAGE_SIZE,
  })
  const [filters, setFilters] = useState<Record<string, string | undefined>>({})

  const { data, isLoading, error, refetch } = useJobs({
    page: pagination.pageIndex + 1,
    pageSize: pagination.pageSize,
    jobType: filters.jobType as JobType | undefined,
    status: filters.status as JobStatus | undefined,
  })

  const cancelJob = useCancelJob()

  const handleCancelJob = async (jobId: string) => {
    await cancelJob.mutateAsync(jobId)
  }

  const columns: ColumnDef<Job>[] = [
    {
      accessorKey: 'job_id',
      header: 'Job ID',
      cell: ({ row }) => (
        <span className="font-mono text-xs">{row.original.job_id.substring(0, 8)}...</span>
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
      accessorKey: 'job_type',
      header: 'Type',
      cell: ({ row }) => (
        <span className="capitalize font-medium">{row.original.job_type}</span>
      ),
    },
    {
      accessorKey: 'params',
      header: 'Model',
      cell: ({ row }) => {
        const modelType = row.original.params?.model_type
        return modelType ? String(modelType) : '-'
      },
    },
    {
      accessorKey: 'created_at',
      header: 'Created',
      cell: ({ row }) => format(new Date(row.original.created_at), 'MMM d, HH:mm'),
    },
    {
      accessorKey: 'completed_at',
      header: 'Completed',
      cell: ({ row }) =>
        row.original.completed_at
          ? format(new Date(row.original.completed_at), 'MMM d, HH:mm')
          : '-',
    },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) => {
        const job = row.original
        if (job.status !== 'pending') return null

        return (
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
        )
      },
    },
  ]

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
        <h1 className="text-3xl font-bold">Jobs</h1>
        <ErrorDisplay error={error} onRetry={refetch} />
      </div>
    )
  }

  const pageCount = data ? Math.ceil(data.total / pagination.pageSize) : 0

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Jobs Monitor</h1>

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
        filterValues={filters}
        onFilterChange={handleFilterChange}
        onReset={handleReset}
        hasActiveFilters={hasActiveFilters}
      />

      <DataTable
        columns={columns}
        data={data?.jobs ?? []}
        pageCount={pageCount}
        pagination={pagination}
        onPaginationChange={setPagination}
        isLoading={isLoading}
        emptyMessage="No jobs found."
      />
    </div>
  )
}
