import { useState } from 'react'
import { Link } from 'react-router-dom'
import { BarChart3, Download, ExternalLink, Loader2, Play } from 'lucide-react'
import { useJob, useCreateJob } from '@/hooks/use-jobs'
import { TimeSeriesChart } from '@/components/charts/time-series-chart'
import { EmptyState } from '@/components/common/error-display'
import { JobPicker } from '@/components/common/job-picker'
import { LoadingState } from '@/components/common/loading-state'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { downloadCsv, toCsv, type CsvColumn } from '@/lib/csv-export'
import { getErrorMessage } from '@/lib/api'
import type { ForecastPoint } from '@/types/api'

/** Horizon presets (days) for an in-page predict run. */
const HORIZON_OPTIONS = [7, 14, 30, 60, 90]

const csvColumns: CsvColumn<ForecastPoint>[] = [
  { key: 'date', header: 'Date' },
  { key: 'forecast', header: 'Forecast' },
  { key: 'lower_bound', header: 'Lower' },
  { key: 'upper_bound', header: 'Upper' },
]

export default function ForecastPage() {
  const [searchJobId, setSearchJobId] = useState('')
  const [trainJobId, setTrainJobId] = useState('')
  const [horizon, setHorizon] = useState(14)
  const [showInterval, setShowInterval] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)

  const { data: job, isLoading, error } = useJob(searchJobId, !!searchJobId)
  const { data: trainJob } = useJob(trainJobId, !!trainJobId)
  const createJob = useCreateJob()

  // A completed `train` job stores result.run_id — the model-artifact key a
  // `predict` job consumes. (This is NOT a registry run id.)
  const trainRunId =
    typeof trainJob?.result?.run_id === 'string' ? trainJob.result.run_id : null

  // A completed `predict` job stores result.forecasts (date + forecast, plus
  // optional lower/upper bounds for models that emit a prediction interval).
  const forecastData = job?.result?.forecasts as ForecastPoint[] | undefined
  const hasBounds = !!forecastData?.some(
    (point) => point.lower_bound != null && point.upper_bound != null,
  )

  async function handleRunForecast() {
    if (!trainRunId) return
    setRunError(null)
    try {
      const newJob = await createJob.mutateAsync({
        job_type: 'predict',
        params: { run_id: trainRunId, horizon },
      })
      setSearchJobId(newJob.job_id)
    } catch (caught) {
      setRunError(getErrorMessage(caught))
    }
  }

  function handleExport() {
    if (!forecastData || !job) return
    downloadCsv(`forecast-${job.job_id}.csv`, toCsv(forecastData, csvColumns))
  }

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Forecast Visualization</h1>

      {/* Run a new forecast in-page */}
      <Card>
        <CardHeader>
          <CardTitle>Run a new forecast</CardTitle>
          <CardDescription>
            Pick a completed training job and a horizon to generate a new prediction.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <JobPicker jobType="train" selectedJobId={trainJobId} onSelect={setTrainJobId} />
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <span className="text-xs text-muted-foreground">Horizon</span>
              <Select value={String(horizon)} onValueChange={(value) => setHorizon(Number(value))}>
                <SelectTrigger className="w-[140px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {HORIZON_OPTIONS.map((days) => (
                    <SelectItem key={days} value={String(days)}>
                      {days} days
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button onClick={handleRunForecast} disabled={!trainRunId || createJob.isPending}>
              {createJob.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Play className="mr-2 h-4 w-4" />
              )}
              Run forecast
            </Button>
          </div>
          {trainJobId && !trainRunId && (
            <p className="text-sm text-muted-foreground">
              The selected training job has no model artifact — pick a completed train job.
            </p>
          )}
          {runError && <p className="text-sm text-destructive">{runError}</p>}
        </CardContent>
      </Card>

      {/* Load an existing forecast */}
      <Card>
        <CardHeader>
          <CardTitle>Load Forecast</CardTitle>
          <CardDescription>
            Pick a completed prediction job to visualize the forecast
          </CardDescription>
        </CardHeader>
        <CardContent>
          <JobPicker
            jobType="predict"
            selectedJobId={searchJobId}
            onSelect={setSearchJobId}
            autoSelectLatest
          />
        </CardContent>
      </Card>

      {/* Results */}
      {isLoading && <LoadingState message="Loading forecast data..." />}

      {error && (
        <Card className="border-destructive">
          <CardContent className="pt-6">
            <p className="text-sm text-destructive">
              Failed to load job. Please check the job ID and try again.
            </p>
          </CardContent>
        </Card>
      )}

      {job && !isLoading && (
        <>
          {/* Job Details */}
          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <CardTitle>Job Details</CardTitle>
                <Button asChild variant="outline" size="sm">
                  <Link to={`/explorer/jobs/${job.job_id}`}>
                    <ExternalLink className="mr-2 h-4 w-4" />
                    View job
                  </Link>
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <div>
                  <dt className="text-muted-foreground">Job ID</dt>
                  <dd className="font-mono">{job.job_id.substring(0, 12)}...</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Status</dt>
                  <dd className="font-medium capitalize">{job.status}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Type</dt>
                  <dd className="capitalize">{job.job_type}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Model</dt>
                  <dd>{String(job.result?.model_type ?? job.params?.model_type ?? '-')}</dd>
                </div>
              </dl>
            </CardContent>
          </Card>

          {/* Forecast Chart */}
          {forecastData && forecastData.length > 0 ? (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <label className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={showInterval}
                    onCheckedChange={(checked) => setShowInterval(checked === true)}
                    disabled={!hasBounds}
                  />
                  Show prediction interval
                  {!hasBounds && (
                    <span className="text-xs text-muted-foreground">
                      (this model emits no interval)
                    </span>
                  )}
                </label>
                <Button variant="outline" size="sm" onClick={handleExport}>
                  <Download className="mr-2 h-4 w-4" />
                  Export CSV
                </Button>
              </div>
              <TimeSeriesChart
                title="Forecast Results"
                description={`${forecastData.length} day forecast`}
                data={forecastData}
                predictedKey="forecast"
                showActual={false}
                showPredicted
                showInterval={showInterval && hasBounds}
                lowerKey="lower_bound"
                upperKey="upper_bound"
              />
            </div>
          ) : job.status === 'completed' && job.job_type === 'predict' ? (
            <Card>
              <CardContent className="pt-6">
                <p className="text-sm text-muted-foreground text-center">
                  No prediction data available in job result.
                </p>
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="pt-6">
                <p className="text-sm text-muted-foreground text-center">
                  {job.status !== 'completed'
                    ? `Job is ${job.status}. Forecast will be available when completed.`
                    : 'This job type does not contain forecast data.'}
                </p>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {!searchJobId && !isLoading && (
        <EmptyState
          title="No forecast loaded"
          description="Run a new forecast above or pick an existing prediction job to visualize the results."
          icon={<BarChart3 className="h-12 w-12" />}
        />
      )}
    </div>
  )
}
