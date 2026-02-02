import { useState } from 'react'
import { useJob } from '@/hooks/use-jobs'
import { TimeSeriesChart } from '@/components/charts/time-series-chart'
import { EmptyState } from '@/components/common/error-display'
import { LoadingState } from '@/components/common/loading-state'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Search, BarChart3 } from 'lucide-react'

export default function ForecastPage() {
  const [jobId, setJobId] = useState('')
  const [searchJobId, setSearchJobId] = useState('')

  const { data: job, isLoading, error } = useJob(searchJobId, !!searchJobId)

  const handleSearch = () => {
    if (jobId.trim()) {
      setSearchJobId(jobId.trim())
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch()
    }
  }

  // Extract forecast data from job result
  const forecastData = job?.result?.predictions as Array<{
    date: string
    predicted: number
  }> | undefined

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Forecast Visualization</h1>

      {/* Search by Job ID */}
      <Card>
        <CardHeader>
          <CardTitle>Load Forecast</CardTitle>
          <CardDescription>
            Enter a completed prediction job ID to visualize the forecast
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            <Input
              placeholder="Enter job ID (e.g., abc12345...)"
              value={jobId}
              onChange={(e) => setJobId(e.target.value)}
              onKeyDown={handleKeyDown}
              className="max-w-md"
            />
            <Button onClick={handleSearch} disabled={!jobId.trim()}>
              <Search className="h-4 w-4 mr-2" />
              Load
            </Button>
          </div>
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
              <CardTitle>Job Details</CardTitle>
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
                  <dd>{String(job.params?.model_type ?? '-')}</dd>
                </div>
              </dl>
            </CardContent>
          </Card>

          {/* Forecast Chart */}
          {forecastData && forecastData.length > 0 ? (
            <TimeSeriesChart
              title="Forecast Results"
              description={`${forecastData.length} day forecast`}
              data={forecastData}
              showActual={false}
              showPredicted={true}
            />
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
          description="Enter a prediction job ID above to visualize the forecast results."
          icon={<BarChart3 className="h-12 w-12" />}
        />
      )}
    </div>
  )
}
