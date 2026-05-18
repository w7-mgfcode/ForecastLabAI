import { useState } from 'react'
import { useJob } from '@/hooks/use-jobs'
import { BacktestFoldsChart, MetricsSummary } from '@/components/charts/backtest-folds-chart'
import { EmptyState } from '@/components/common/error-display'
import { JobPicker } from '@/components/common/job-picker'
import { LoadingState } from '@/components/common/loading-state'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { LineChart } from 'lucide-react'

interface BacktestResult {
  aggregated_metrics: {
    mae_mean: number
    smape_mean: number
    wape_mean: number
    bias_mean: number
    stability_index: number
  }
  fold_metrics: Array<{
    fold: number
    mae: number
    smape: number
    wape: number
    bias: number
  }>
  baseline_comparison?: {
    naive: { mae: number; improvement_pct: number }
    seasonal_naive: { mae: number; improvement_pct: number }
  }
}

export default function BacktestPage() {
  const [searchJobId, setSearchJobId] = useState('')
  const [selectedMetric, setSelectedMetric] = useState<'mae' | 'smape' | 'wape' | 'bias'>('mae')

  const { data: job, isLoading, error } = useJob(searchJobId, !!searchJobId)

  // Extract backtest result from job
  const backtestResult = job?.result as BacktestResult | undefined

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Backtest Results</h1>

      {/* Job picker */}
      <Card>
        <CardHeader>
          <CardTitle>Load Backtest</CardTitle>
          <CardDescription>
            Pick a completed backtest job to visualize the results
          </CardDescription>
        </CardHeader>
        <CardContent>
          <JobPicker
            jobType="backtest"
            selectedJobId={searchJobId}
            onSelect={setSearchJobId}
            autoSelectLatest
          />
        </CardContent>
      </Card>

      {/* Results */}
      {isLoading && <LoadingState message="Loading backtest results..." />}

      {error && (
        <Card className="border-destructive">
          <CardContent className="pt-6">
            <p className="text-sm text-destructive">
              Failed to load job. Please check the job ID and try again.
            </p>
          </CardContent>
        </Card>
      )}

      {job && backtestResult && !isLoading && (
        <>
          {/* Aggregated Metrics */}
          <Card>
            <CardHeader>
              <CardTitle>Aggregated Metrics</CardTitle>
              <CardDescription>
                Mean metrics across all {backtestResult.fold_metrics?.length ?? 0} folds
              </CardDescription>
            </CardHeader>
            <CardContent>
              <MetricsSummary
                metrics={[
                  {
                    label: 'MAE',
                    value: backtestResult.aggregated_metrics?.mae_mean ?? 0,
                    description: 'Mean Absolute Error',
                  },
                  {
                    label: 'sMAPE',
                    value: backtestResult.aggregated_metrics?.smape_mean ?? 0,
                    unit: '%',
                    description: 'Symmetric MAPE (0-200)',
                  },
                  {
                    label: 'WAPE',
                    value: backtestResult.aggregated_metrics?.wape_mean ?? 0,
                    unit: '%',
                    description: 'Weighted APE',
                  },
                  {
                    label: 'Stability',
                    value: backtestResult.aggregated_metrics?.stability_index ?? 0,
                    unit: '%',
                    description: 'Lower is better',
                  },
                ]}
              />
            </CardContent>
          </Card>

          {/* Baseline Comparison */}
          {backtestResult.baseline_comparison && (
            <Card>
              <CardHeader>
                <CardTitle>Baseline Comparison</CardTitle>
                <CardDescription>Performance vs naive baselines</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-6">
                  <div>
                    <p className="text-sm font-medium mb-1">vs Naive</p>
                    <p className="text-2xl font-bold">
                      {backtestResult.baseline_comparison.naive.improvement_pct > 0 ? '+' : ''}
                      {backtestResult.baseline_comparison.naive.improvement_pct.toFixed(1)}%
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Naive MAE: {backtestResult.baseline_comparison.naive.mae.toFixed(2)}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm font-medium mb-1">vs Seasonal Naive</p>
                    <p className="text-2xl font-bold">
                      {backtestResult.baseline_comparison.seasonal_naive.improvement_pct > 0 ? '+' : ''}
                      {backtestResult.baseline_comparison.seasonal_naive.improvement_pct.toFixed(1)}%
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Seasonal MAE: {backtestResult.baseline_comparison.seasonal_naive.mae.toFixed(2)}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Fold Metrics Chart */}
          {backtestResult.fold_metrics && backtestResult.fold_metrics.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Metrics by Fold</CardTitle>
                <CardDescription>Performance variation across CV folds</CardDescription>
              </CardHeader>
              <CardContent>
                <Tabs value={selectedMetric} onValueChange={(v) => setSelectedMetric(v as typeof selectedMetric)}>
                  <TabsList className="mb-4">
                    <TabsTrigger value="mae">MAE</TabsTrigger>
                    <TabsTrigger value="smape">sMAPE</TabsTrigger>
                    <TabsTrigger value="wape">WAPE</TabsTrigger>
                    <TabsTrigger value="bias">Bias</TabsTrigger>
                  </TabsList>
                  <TabsContent value={selectedMetric}>
                    <BacktestFoldsChart
                      title=""
                      data={backtestResult.fold_metrics}
                      metricKey={selectedMetric}
                      height={300}
                    />
                  </TabsContent>
                </Tabs>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {job && !backtestResult && !isLoading && (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground text-center">
              {job.status !== 'completed'
                ? `Job is ${job.status}. Results will be available when completed.`
                : 'This job does not contain backtest results.'}
            </p>
          </CardContent>
        </Card>
      )}

      {!searchJobId && !isLoading && (
        <EmptyState
          title="No backtest loaded"
          description="Pick a backtest job above to visualize the cross-validation results."
          icon={<LineChart className="h-12 w-12" />}
        />
      )}
    </div>
  )
}
