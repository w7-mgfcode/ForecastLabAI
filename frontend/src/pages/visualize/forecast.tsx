import { useState } from 'react'
import { format } from 'date-fns'
import { DateRange } from 'react-day-picker'
import { Link } from 'react-router-dom'
import { BarChart3, Download, ExternalLink, Loader2, Play } from 'lucide-react'
import { useJob, useCreateJob } from '@/hooks/use-jobs'
import { useJobExplanation } from '@/hooks/use-explanations'
import { useJobFeatureMetadata } from '@/hooks/use-feature-metadata'
import { useStores } from '@/hooks/use-stores'
import { useProducts } from '@/hooks/use-products'
import { ExplanationPanel } from '@/components/explainability/explanation-panel'
import { FeatureImportancePanel } from '@/components/explainability/feature-importance-panel'
import { ModelFamilyBadge } from '@/components/common/model-family-badge'
import { DateRangePicker } from '@/components/common/date-range-picker'
import { ModelFamilyTabs } from '@/components/forecast-intelligence/model-family-tabs'
import { ModelTypeSelect } from '@/components/forecast-intelligence/model-type-select'
import { MODEL_FAMILY_MAP } from '@/components/forecast-intelligence/model-type-utils'
import { FeatureFrameSelect } from '@/components/forecast-intelligence/feature-frame-select'
import { FeatureGroupsToggle } from '@/components/forecast-intelligence/feature-groups-toggle'
import { defaultV2Groups } from '@/lib/feature-frame-utils'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
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
import { FEATURE_GROUP_VALUES } from '@/types/api'
import { downloadCsv, toCsv, type CsvColumn } from '@/lib/csv-export'
import { getErrorMessage } from '@/lib/api'
import type {
  FeatureFrameVersion,
  FeatureGroup,
  ForecastPoint,
  ModelFamily,
} from '@/types/api'

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

  // PRP-37 Slice C — train-from-page control row state.
  const [trainFamily, setTrainFamily] = useState<ModelFamily>('baseline')
  const [trainModelType, setTrainModelType] = useState<string>('seasonal_naive')
  const [trainStoreId, setTrainStoreId] = useState('')
  const [trainProductId, setTrainProductId] = useState('')
  const [trainDateRange, setTrainDateRange] = useState<DateRange | undefined>()
  const [trainVersion, setTrainVersion] = useState<FeatureFrameVersion>(1)
  const [trainGroups, setTrainGroups] = useState<FeatureGroup[]>([])
  const [trainError, setTrainError] = useState<string | null>(null)

  const storesQuery = useStores({ page: 1, pageSize: 100 })
  const productsQuery = useProducts({ page: 1, pageSize: 100 })

  // V2 is meaningful only for feature-aware families. Baselines do not consume
  // features, so the V2 option is locked off there.
  const isV2Available = trainFamily !== 'baseline'

  const { data: job, isLoading, error } = useJob(searchJobId, !!searchJobId)
  const { data: trainJob } = useJob(trainJobId, !!trainJobId)
  const createJob = useCreateJob()

  // A completed `train` job stores result.run_id — the model-artifact key a
  // `predict` job consumes. (This is NOT a registry run id.)
  const trainRunId =
    typeof trainJob?.result?.run_id === 'string' ? trainJob.result.run_id : null

  // A completed `predict` job stores result.forecasts (date + forecast, plus
  // optional lower/upper bounds for models that emit a prediction interval).
  // `job.result` is untyped JSONB — guard with Array.isArray before treating
  // `forecasts` as an array so a malformed result can never throw on `.some()`.
  const rawForecasts = job?.result?.forecasts
  const forecastData: ForecastPoint[] = Array.isArray(rawForecasts)
    ? (rawForecasts as ForecastPoint[])
    : []
  const hasBounds = forecastData.some(
    (point) => point.lower_bound != null && point.upper_bound != null,
  )

  // Explain the loaded job only when it is a completed predict job.
  const isPredictDone = job?.status === 'completed' && job?.job_type === 'predict'
  const explanationQuery = useJobExplanation(job?.job_id ?? '', !!job && isPredictDone)

  // MLZOO-D / PRP-31 — feature-importance for the train job that produced
  // the loaded predict. CRITICAL: forecast.tsx never has a registry run_id;
  // `trainJob.result.run_id` (line 49 above) is the FORECAST-ARTIFACT KEY
  // (`uuid.uuid4().hex[:12]`, see `app/features/forecasting/service.py:270`),
  // NOT a registry UUID. Calling `useRunFeatureMetadata(trainRunId, ...)`
  // would 404 because `/forecasting/runs/{run_id}` treats `{run_id}` as a
  // registry UUID. We use the job-keyed sibling
  // (`/forecasting/jobs/{job_id}/feature-metadata`) which loads the bundle
  // from `job.result.model_path` directly. Recorded in memory
  // `[[scenario-run-id-vs-registry-run-id]]`.
  const trainJobMetadata = useJobFeatureMetadata(trainJobId, !!trainJobId)
  const loadedTrainFamily = trainJobMetadata.data?.model_family

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

  /** PRP-37 — narrow trainModelType to the picked family. */
  function handleFamilyChange(next: ModelFamily) {
    setTrainFamily(next)
    const valid = MODEL_FAMILY_MAP[next]
    if (!valid.includes(trainModelType)) {
      setTrainModelType(valid[0] ?? '')
    }
    if (next === 'baseline') {
      // Baseline cannot consume features — drop V2 + groups when switching back.
      setTrainVersion(1)
      setTrainGroups([])
    }
  }

  function handleVersionChange(next: FeatureFrameVersion) {
    setTrainVersion(next)
    if (next === 1) {
      setTrainGroups([])
    } else if (trainGroups.length === 0) {
      setTrainGroups(defaultV2Groups())
    }
  }

  const trainFormReady =
    !!trainStoreId &&
    !!trainProductId &&
    !!trainDateRange?.from &&
    !!trainDateRange?.to &&
    !!trainModelType

  async function handleSubmitTrain() {
    if (!trainFormReady || !trainDateRange?.from || !trainDateRange?.to) return
    setTrainError(null)
    const params: Record<string, unknown> = {
      model_type: trainModelType,
      store_id: Number(trainStoreId),
      product_id: Number(trainProductId),
      start_date: format(trainDateRange.from, 'yyyy-MM-dd'),
      end_date: format(trainDateRange.to, 'yyyy-MM-dd'),
    }
    // Backend treats V1 + omit-feature_groups as the default — only forward the
    // new fields when the operator explicitly opted into V2.
    if (trainVersion === 2) {
      params.feature_frame_version = 2
      if (trainGroups.length > 0) {
        params.feature_groups = trainGroups
      }
    }
    try {
      const newJob = await createJob.mutateAsync({
        job_type: 'train',
        params,
      })
      setTrainJobId(newJob.job_id)
    } catch (caught) {
      setTrainError(getErrorMessage(caught))
    }
  }

  function handleExport() {
    if (forecastData.length === 0 || !job) return
    downloadCsv(`forecast-${job.job_id}.csv`, toCsv(forecastData, csvColumns))
  }

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Forecast Visualization</h1>

      {/* PRP-37 Slice C — segmented control row to train a new model. */}
      <Card>
        <CardHeader>
          <CardTitle>Train a new model</CardTitle>
          <CardDescription>
            Pick a family, a model, a store/product/date window. V2 unlocks
            feature-aware models (tree + additive); V1 is target-only.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <span className="text-xs text-muted-foreground">Family</span>
              <ModelFamilyTabs
                family={trainFamily}
                onChange={handleFamilyChange}
              />
            </div>
            <div className="space-y-1">
              <span className="text-xs text-muted-foreground">Model</span>
              <ModelTypeSelect
                family={trainFamily}
                value={trainModelType}
                onChange={setTrainModelType}
                className="w-[260px]"
              />
            </div>
            <div className="space-y-1">
              <span className="text-xs text-muted-foreground">Feature frame</span>
              <FeatureFrameSelect
                value={trainVersion}
                onChange={handleVersionChange}
                isV2Available={isV2Available}
                v2DisabledReason={
                  trainFamily === 'baseline'
                    ? 'Baseline models do not consume features — V2 is meaningful for tree and additive families only.'
                    : undefined
                }
              />
            </div>
          </div>
          {trainVersion === 2 && isV2Available && (
            <FeatureGroupsToggle
              value={trainGroups}
              onChange={setTrainGroups}
              availableGroups={[...FEATURE_GROUP_VALUES]}
              defaults={defaultV2Groups()}
            />
          )}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div className="space-y-1">
              <span className="text-xs text-muted-foreground">Store</span>
              <Select value={trainStoreId} onValueChange={setTrainStoreId}>
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
              <Select value={trainProductId} onValueChange={setTrainProductId}>
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
              <span className="text-xs text-muted-foreground">Date window</span>
              <DateRangePicker
                value={trainDateRange}
                onChange={setTrainDateRange}
              />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Button
              onClick={handleSubmitTrain}
              disabled={!trainFormReady || createJob.isPending}
            >
              {createJob.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Play className="mr-2 h-4 w-4" />
              )}
              Train model
            </Button>
            {!trainFormReady && (
              <span className="text-sm text-muted-foreground">
                Pick a model, store, product and date window to enable.
              </span>
            )}
          </div>
          {trainError && <p className="text-sm text-destructive">{trainError}</p>}
        </CardContent>
      </Card>

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
          {forecastData.length > 0 ? (
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

          {/* Forecast explanation — only for a completed predict job */}
          {isPredictDone && (
            <ExplanationPanel
              explanation={explanationQuery.data}
              isLoading={explanationQuery.isLoading}
              error={explanationQuery.error}
            />
          )}

          {/* MLZOO-D — collapsible feature-importance panel for the train job. */}
          {trainJobId && (
            <Collapsible defaultOpen={false}>
              <Card>
                <CardHeader>
                  <CollapsibleTrigger className="flex w-full items-center justify-between gap-2">
                    <CardTitle className="flex items-center gap-2 text-base">
                      Model details
                      {loadedTrainFamily ? (
                        <ModelFamilyBadge family={loadedTrainFamily} />
                      ) : null}
                    </CardTitle>
                    <span className="text-xs text-muted-foreground">
                      Expand to see the trained model&apos;s feature importance.
                    </span>
                  </CollapsibleTrigger>
                </CardHeader>
                <CollapsibleContent>
                  <CardContent>
                    <FeatureImportancePanel
                      data={trainJobMetadata.data}
                      isLoading={trainJobMetadata.isLoading}
                      error={trainJobMetadata.error}
                    />
                  </CardContent>
                </CollapsibleContent>
              </Card>
            </Collapsible>
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
