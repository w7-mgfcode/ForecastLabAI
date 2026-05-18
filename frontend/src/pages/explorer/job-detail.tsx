import { Link, useParams } from 'react-router-dom'
import { format } from 'date-fns'
import { ArrowLeft, Loader2, XCircle } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { useJob, useCancelJob } from '@/hooks/use-jobs'
import { JsonBlock } from '@/components/common/json-block'
import { ErrorDisplay } from '@/components/common/error-display'
import { LoadingState } from '@/components/common/loading-state'
import { StatusBadge } from '@/components/common/status-badge'
import { getStatusVariant } from '@/lib/status-utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
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
import { ROUTES } from '@/lib/constants'

function fmtDate(value: string | null | undefined): string {
  return value ? format(new Date(value), 'MMM d, yyyy HH:mm') : '—'
}

function Field({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="font-medium">{children}</dd>
    </div>
  )
}

export default function JobDetailPage() {
  const { jobId } = useParams()
  // useJob already polls every 2s while the job is pending/running.
  const jobQuery = useJob(jobId ?? '', !!jobId)
  const cancelJob = useCancelJob()
  const queryClient = useQueryClient()

  if (!jobId) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Job Detail</h1>
        <ErrorDisplay error={new Error('No job id in the URL.')} title="Invalid job" />
      </div>
    )
  }

  if (jobQuery.error) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Job Detail</h1>
        <ErrorDisplay error={jobQuery.error} onRetry={() => void jobQuery.refetch()} />
      </div>
    )
  }

  if (jobQuery.isLoading || !jobQuery.data) {
    return <LoadingState message="Loading job..." />
  }

  const job = jobQuery.data

  async function handleCancel() {
    // mutateAsync rejects on failure — catch it so a cancel error surfaces as
    // a toast instead of an unhandled promise rejection.
    try {
      await cancelJob.mutateAsync(jobId)
      // useCancelJob invalidates ['jobs']; refresh this detail query explicitly
      // so the page reflects the cancelled status immediately.
      void queryClient.invalidateQueries({ queryKey: ['jobs', jobId] })
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to cancel job')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="space-y-1">
          <Button asChild variant="ghost" size="sm" className="-ml-2 h-7">
            <Link to={ROUTES.EXPLORER.JOBS}>
              <ArrowLeft className="mr-1 h-4 w-4" />
              Back to Jobs
            </Link>
          </Button>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="break-all font-mono text-2xl font-bold">{job.job_id}</h1>
            <StatusBadge variant={getStatusVariant(job.status)}>{job.status}</StatusBadge>
          </div>
          <p className="text-sm capitalize text-muted-foreground">{job.job_type} job</p>
        </div>
        {job.status === 'pending' && (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive" disabled={cancelJob.isPending}>
                {cancelJob.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <XCircle className="mr-2 h-4 w-4" />
                )}
                Cancel job
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
                <AlertDialogAction onClick={() => void handleCancel()}>
                  Yes, cancel
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Job profile</CardTitle>
          <CardDescription>Execution record for this job.</CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            <Field label="Type">
              <span className="capitalize">{job.job_type}</span>
            </Field>
            <Field label="Status">
              <span className="capitalize">{job.status}</span>
            </Field>
            <Field label="Run">
              {job.run_id ? (
                <Link
                  className="break-all font-mono text-sm text-primary hover:underline"
                  to={`/explorer/runs/${job.run_id}`}
                >
                  {job.run_id}
                </Link>
              ) : (
                '—'
              )}
            </Field>
            <Field label="Created">{fmtDate(job.created_at)}</Field>
            <Field label="Started">{fmtDate(job.started_at)}</Field>
            <Field label="Completed">{fmtDate(job.completed_at)}</Field>
          </dl>
        </CardContent>
      </Card>

      {job.status === 'failed' && (
        <Card className="border-destructive/50">
          <CardHeader>
            <CardTitle className="text-destructive">Error</CardTitle>
            {job.error_type && (
              <CardDescription className="font-mono text-destructive/80">
                {job.error_type}
              </CardDescription>
            )}
          </CardHeader>
          <CardContent>
            <p className="text-sm text-destructive/90">
              {job.error_message ?? 'The job failed without an error message.'}
            </p>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Parameters</CardTitle>
          <CardDescription>Input configuration this job ran with.</CardDescription>
        </CardHeader>
        <CardContent>
          <JsonBlock value={job.params} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Result</CardTitle>
          <CardDescription>Output payload produced by the job.</CardDescription>
        </CardHeader>
        <CardContent>
          {job.result == null ? (
            <p className="text-sm text-muted-foreground">
              {job.status === 'pending' || job.status === 'running'
                ? 'No result yet — the job is still running.'
                : 'This job produced no result.'}
            </p>
          ) : (
            <JsonBlock value={job.result} />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
