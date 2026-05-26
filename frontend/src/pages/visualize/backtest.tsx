import { useState } from 'react'
import { Link } from 'react-router-dom'
import { format } from 'date-fns'
import { DateRange } from 'react-day-picker'
import { Download, ExternalLink, LineChart, Loader2, Play } from 'lucide-react'
import { useJob, useCreateJob } from '@/hooks/use-jobs'
import { useStores } from '@/hooks/use-stores'
import { useProducts } from '@/hooks/use-products'
import { BacktestFoldsChart, MetricsSummary } from '@/components/charts/backtest-folds-chart'
import { BacktestHorizonBucketsChart } from '@/components/charts/backtest-horizon-buckets-chart'
import { DateRangePicker } from '@/components/common/date-range-picker'
import { EmptyState } from '@/components/common/error-display'
import { JobPicker } from '@/components/common/job-picker'
import { LoadingState } from '@/components/common/loading-state'
import { ModelFamilyTabs } from '@/components/forecast-intelligence/model-family-tabs'
import { ModelTypeSelect } from '@/components/forecast-intelligence/model-type-select'
import { MODEL_FAMILY_MAP } from '@/components/forecast-intelligence/model-type-utils'
import { HorizonBucketTable } from '@/components/forecast-intelligence/horizon-bucket-table'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { downloadCsv, toCsv, type CsvColumn } from '@/lib/csv-export'
import { getErrorMessage } from '@/lib/api'
import type {
  BacktestResponse,
  ModelBacktestResult,
  ModelFamily,
} from '@/types/api'

interface FoldMetric {
  fold: number
  mae: number
  smape: number
  wape: number
  bias: number
}

interface BacktestResult {
  aggregated_metrics: {
    mae_mean: number
    smape_mean: number
    wape_mean: number
    bias_mean: number
    stability_index: number
  }
  fold_metrics: FoldMetric[]
  baseline_comparison?: {
    naive: { mae: number; improvement_pct: number }
    seasonal_naive: { mae: number; improvement_pct: number }
  }
}

/** Format a metric value to 2 decimal places; '—' when missing. */
function fmt(value: number | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  return value.toFixed(2)
}

const foldCsvColumns: CsvColumn<FoldMetric>[] = [
  { key: 'fold', header: 'Fold' },
  { key: 'mae', header: 'MAE' },
  { key: 'smape', header: 'sMAPE' },
  { key: 'wape', header: 'WAPE' },
  { key: 'bias', header: 'Bias' },
]

export default function BacktestPage() {
  const [searchJobId, setSearchJobId] = useState('')
  const [selectedMetric, setSelectedMetric] = useState<'mae' | 'smape' | 'wape' | 'bias'>('mae')

  // In-page "Run new backtest" form state.
  const [storeId, setStoreId] = useState('')
  const [productId, setProductId] = useState('')
  // PRP-37 — split the flat model select into family + filtered type.
  const [family, setFamily] = useState<ModelFamily>('baseline')
  const [modelType, setModelType] = useState('naive')
  const [dateRange, setDateRange] = useState<DateRange | undefined>()
  const [nSplits, setNSplits] = useState(5)
  const [testSize, setTestSize] = useState(14)
  const [runError, setRunError] = useState<string | null>(null)
  // PRP-37 — per-horizon-bucket viz metric switcher (PRP-36).
  const [bucketMetric, setBucketMetric] = useState<
    'mae' | 'smape' | 'wape' | 'bias' | 'rmse'
  >('wape')

  const { data: job, isLoading, error } = useJob(searchJobId, !!searchJobId)
  const createJob = useCreateJob()
  // /dimensions/{stores,products} both cap page_size at 100.
  const storesQuery = useStores({ page: 1, pageSize: 100 })
  const productsQuery = useProducts({ page: 1, pageSize: 100 })

  // Extract backtest result from job. job.result is JSONB so we read it
  // optimistically — the legacy `aggregated_metrics.mae_mean` shape and the
  // PRP-36 `main_model_results.aggregated_metrics["mae"]` shape coexist in
  // the registry.
  const backtestResult = job?.result as BacktestResult | undefined
  const prp36 = job?.result as Partial<BacktestResponse> | undefined
  const mainResult: ModelBacktestResult | undefined = prp36?.main_model_results
  const baselineResults: ModelBacktestResult[] = prp36?.baseline_results ?? []
  const rmse = mainResult?.aggregated_metrics?.['rmse']
  const bucketed = mainResult?.bucketed_aggregated_metrics ?? null

  function handleFamilyChange(next: ModelFamily) {
    setFamily(next)
    const valid = MODEL_FAMILY_MAP[next]
    if (!valid.includes(modelType)) {
      setModelType(valid[0] ?? '')
    }
  }

  // The number inputs can be cleared to 0; require a valid split count and
  // test size so an invalid backtest config can never be submitted.
  const formReady =
    !!storeId &&
    !!productId &&
    !!dateRange?.from &&
    !!dateRange?.to &&
    nSplits >= 2 &&
    testSize >= 1

  async function handleRunBacktest() {
    if (!storeId || !productId || !dateRange?.from || !dateRange?.to) return
    setRunError(null)
    try {
      const newJob = await createJob.mutateAsync({
        job_type: 'backtest',
        params: {
          model_type: modelType,
          store_id: Number(storeId),
          product_id: Number(productId),
          start_date: format(dateRange.from, 'yyyy-MM-dd'),
          end_date: format(dateRange.to, 'yyyy-MM-dd'),
          n_splits: nSplits,
          test_size: testSize,
        },
      })
      setSearchJobId(newJob.job_id)
    } catch (caught) {
      setRunError(getErrorMessage(caught))
    }
  }

  function handleExport() {
    if (!backtestResult?.fold_metrics || !job) return
    downloadCsv(
      `backtest-${job.job_id}.csv`,
      toCsv(backtestResult.fold_metrics, foldCsvColumns),
    )
  }

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Backtest Results</h1>

      {/* Run a new backtest in-page */}
      <Card>
        <CardHeader>
          <CardTitle>Run a new backtest</CardTitle>
          <CardDescription>
            Pick a store, product, model and date window to run time-series cross-validation.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div className="space-y-1">
              <span className="text-xs text-muted-foreground">Store</span>
              <Select value={storeId} onValueChange={setStoreId}>
                <SelectTrigger>
                  <SelectValue placeholder="Pick a store…" />
                </SelectTrigger>
                <SelectContent>
                  {(storesQuery.data?.stores ?? []).map((store) => (
                    <SelectItem key={store.id} value={String(store.id)}>
                      {store.code} · {store.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <span className="text-xs text-muted-foreground">Product</span>
              <Select value={productId} onValueChange={setProductId}>
                <SelectTrigger>
                  <SelectValue placeholder="Pick a product…" />
                </SelectTrigger>
                <SelectContent>
                  {(productsQuery.data?.products ?? []).map((product) => (
                    <SelectItem key={product.id} value={String(product.id)}>
                      {product.sku} · {product.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <span className="text-xs text-muted-foreground">Family</span>
              <ModelFamilyTabs family={family} onChange={handleFamilyChange} />
            </div>
            <div className="space-y-1">
              <span className="text-xs text-muted-foreground">Model</span>
              <ModelTypeSelect
                family={family}
                value={modelType}
                onChange={setModelType}
                className="w-full"
              />
            </div>
            <div className="space-y-1">
              <span className="text-xs text-muted-foreground">Date window</span>
              <DateRangePicker value={dateRange} onChange={setDateRange} />
            </div>
            <div className="space-y-1">
              <span className="text-xs text-muted-foreground">Splits</span>
              <Input
                type="number"
                min={2}
                value={String(nSplits)}
                onChange={(event) => setNSplits(Number(event.target.value) || 0)}
              />
            </div>
            <div className="space-y-1">
              <span className="text-xs text-muted-foreground">Test size (days)</span>
              <Input
                type="number"
                min={1}
                value={String(testSize)}
                onChange={(event) => setTestSize(Number(event.target.value) || 0)}
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button onClick={handleRunBacktest} disabled={!formReady || createJob.isPending}>
              {createJob.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Play className="mr-2 h-4 w-4" />
              )}
              Run backtest
            </Button>
            {!formReady && (
              <span className="text-sm text-muted-foreground">
                Pick a store, product and date window, with at least 2 splits and a 1-day test
                size, to enable.
              </span>
            )}
          </div>
          {runError && <p className="text-sm text-destructive">{runError}</p>}
        </CardContent>
      </Card>

      {/* Load an existing backtest */}
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
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <CardTitle>Aggregated Metrics</CardTitle>
                  <CardDescription>
                    Mean metrics across all {backtestResult.fold_metrics?.length ?? 0} folds
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <Button asChild variant="outline" size="sm">
                    <Link to={`/explorer/jobs/${job.job_id}`}>
                      <ExternalLink className="mr-2 h-4 w-4" />
                      View job
                    </Link>
                  </Button>
                  <Button variant="outline" size="sm" onClick={handleExport}>
                    <Download className="mr-2 h-4 w-4" />
                    Export CSV
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <MetricsSummary
                metrics={[
                  {
                    label: 'MAE',
                    value:
                      mainResult?.aggregated_metrics?.['mae'] ??
                      backtestResult.aggregated_metrics?.mae_mean ??
                      0,
                    description: 'Mean Absolute Error',
                  },
                  {
                    label: 'sMAPE',
                    value:
                      mainResult?.aggregated_metrics?.['smape'] ??
                      backtestResult.aggregated_metrics?.smape_mean ??
                      0,
                    unit: '%',
                    description: 'Symmetric MAPE (0-200)',
                  },
                  {
                    label: 'WAPE',
                    value:
                      mainResult?.aggregated_metrics?.['wape'] ??
                      backtestResult.aggregated_metrics?.wape_mean ??
                      0,
                    unit: '%',
                    description: 'Weighted APE',
                  },
                  // PRP-37 — RMSE is a key inside aggregated_metrics (PRP-36).
                  // Omit entirely when absent rather than zero-padding.
                  ...(typeof rmse === 'number'
                    ? [
                        {
                          label: 'RMSE',
                          value: rmse,
                          description: 'Root mean squared error',
                        },
                      ]
                    : [
                        {
                          label: 'Stability',
                          value:
                            backtestResult.aggregated_metrics?.stability_index ?? 0,
                          unit: '%',
                          description: 'Lower is better',
                        },
                      ]),
                ]}
              />
            </CardContent>
          </Card>

          {/* PRP-37 — Per-horizon-bucket metrics (PRP-36). Rendered only when
              the backend emits bucketed_aggregated_metrics. */}
          {bucketed && Object.keys(bucketed).length > 0 && (
            <Card>
              <CardHeader>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <CardTitle>Per-horizon-bucket metrics</CardTitle>
                    <CardDescription>
                      Forecast error split by horizon distance. Near-horizon
                      buckets typically improve faster than far-horizon ones.
                    </CardDescription>
                  </div>
                  <Select
                    value={bucketMetric}
                    onValueChange={(value) =>
                      setBucketMetric(value as typeof bucketMetric)
                    }
                  >
                    <SelectTrigger className="w-[140px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="mae">MAE</SelectItem>
                      <SelectItem value="smape">sMAPE</SelectItem>
                      <SelectItem value="wape">WAPE</SelectItem>
                      <SelectItem value="bias">Bias</SelectItem>
                      <SelectItem value="rmse">RMSE</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </CardHeader>
              <CardContent className="grid gap-4 md:grid-cols-2">
                <HorizonBucketTable
                  bucketed={bucketed}
                  metric={bucketMetric}
                  metricLabel={bucketMetric.toUpperCase()}
                />
                <BacktestHorizonBucketsChart
                  bucketed={bucketed}
                  metric={bucketMetric}
                  title="Bucketed view"
                />
              </CardContent>
            </Card>
          )}

          {/* PRP-37 — Baseline vs. feature-aware comparison (PRP-36). Shown
              only when the response includes one or more baseline ModelBacktestResult
              rows. */}
          {baselineResults.length > 0 && mainResult && (
            <Card>
              <CardHeader>
                <CardTitle>Baseline vs feature-aware</CardTitle>
                <CardDescription>
                  Same folds, identical splits — every baseline competes against
                  the main feature-aware model. Lower WAPE / RMSE wins.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left">
                      <th className="py-1.5">Model</th>
                      <th className="py-1.5 text-right">MAE</th>
                      <th className="py-1.5 text-right">sMAPE</th>
                      <th className="py-1.5 text-right">WAPE</th>
                      <th className="py-1.5 text-right">RMSE</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="border-t font-medium">
                      <td className="py-1.5">{mainResult.model_type} (main)</td>
                      <td className="py-1.5 text-right tabular-nums">
                        {fmt(mainResult.aggregated_metrics?.['mae'])}
                      </td>
                      <td className="py-1.5 text-right tabular-nums">
                        {fmt(mainResult.aggregated_metrics?.['smape'])}
                      </td>
                      <td className="py-1.5 text-right tabular-nums">
                        {fmt(mainResult.aggregated_metrics?.['wape'])}
                      </td>
                      <td className="py-1.5 text-right tabular-nums">
                        {fmt(mainResult.aggregated_metrics?.['rmse'])}
                      </td>
                    </tr>
                    {baselineResults.map((b) => (
                      <tr key={b.model_type} className="border-t">
                        <td className="text-muted-foreground py-1.5">
                          {b.model_type}
                        </td>
                        <td className="py-1.5 text-right tabular-nums">
                          {fmt(b.aggregated_metrics?.['mae'])}
                        </td>
                        <td className="py-1.5 text-right tabular-nums">
                          {fmt(b.aggregated_metrics?.['smape'])}
                        </td>
                        <td className="py-1.5 text-right tabular-nums">
                          {fmt(b.aggregated_metrics?.['wape'])}
                        </td>
                        <td className="py-1.5 text-right tabular-nums">
                          {fmt(b.aggregated_metrics?.['rmse'])}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          )}

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
          description="Run a new backtest above or pick a backtest job to visualize the cross-validation results."
          icon={<LineChart className="h-12 w-12" />}
        />
      )}
    </div>
  )
}
