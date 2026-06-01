import { useMemo, useState } from 'react'
import { format } from 'date-fns'
import { DateRange } from 'react-day-picker'
import { Trophy } from 'lucide-react'
import { useStores } from '@/hooks/use-stores'
import { useProducts } from '@/hooks/use-products'
import { useModelCatalog, usePairAvailability } from '@/hooks/use-model-selection'
import { DateRangePicker } from '@/components/common/date-range-picker'
import { ErrorDisplay } from '@/components/common/error-display'
import { AvailabilityPanel } from '@/components/champion-selector/availability-panel'
import { BacktestSettingsForm } from '@/components/champion-selector/backtest-settings-form'
import { splitConfigErrors } from '@/components/champion-selector/split-config'
import { CandidateModelPicker } from '@/components/champion-selector/candidate-model-picker'
import { SearchableEntitySelect } from '@/components/champion-selector/searchable-entity-select'
import { RUN_COMPARISON_PENDING } from '@/components/champion-selector/copy'
import { assembleRunRequest } from '@/components/champion-selector/run-request'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import type {
  ModelSelectionRunRequest,
  SplitConfig,
} from '@/types/api'

const DEFAULT_HORIZON = 14

const DEFAULT_SPLIT: SplitConfig = {
  strategy: 'expanding',
  n_splits: 5,
  min_train_size: 30,
  gap: 0,
  horizon: DEFAULT_HORIZON,
}

/**
 * Forecast Champion Selector — Slice A.
 *
 * Configuration + availability triage only. It assembles a typed
 * `ModelSelectionRunRequest` in component state and surfaces a DISABLED
 * "Run comparison" CTA — the comparison RUN itself (and all results/training)
 * lands in Slices B/C. This page calls only the two read GETs (catalog +
 * availability); it never POSTs.
 */
export default function ChampionSelectorPage() {
  const [storeId, setStoreId] = useState<number | null>(null)
  const [productId, setProductId] = useState<number | null>(null)
  const [dateRange, setDateRange] = useState<DateRange | undefined>()
  const [forecastHorizon, setForecastHorizon] = useState(DEFAULT_HORIZON)
  const [splitConfig, setSplitConfig] = useState<SplitConfig>(DEFAULT_SPLIT)
  const [rankingMetric, setRankingMetric] = useState<
    ModelSelectionRunRequest['ranking_metric']
  >('wape')
  // `null` means "the user hasn't edited the selection yet" — fall back to the
  // catalog's default candidate set (derived below, no effect needed).
  const [editedModels, setEditedModels] = useState<string[] | null>(null)

  // /dimensions/{stores,products} both cap page_size at 100 (client-filtered).
  const storesQuery = useStores({ page: 1, pageSize: 100 })
  const productsQuery = useProducts({ page: 1, pageSize: 100 })
  const catalogQuery = useModelCatalog()

  const validPair = !!storeId && !!productId
  const availabilityQuery = usePairAvailability({
    storeId,
    productId,
    forecastHorizon,
    enabled: validPair,
  })

  // Pre-select the backend default candidate set until the user edits it —
  // derived during render rather than seeded via an effect.
  const selectedModels =
    editedModels ?? catalogQuery.data?.default_candidate_model_types ?? []

  // split_config.horizon must equal forecast_horizon (the backend validator).
  // Force it during render so no effect is needed to keep them in sync.
  const effectiveSplit: SplitConfig = useMemo(
    () => ({ ...splitConfig, horizon: forecastHorizon }),
    [splitConfig, forecastHorizon],
  )

  const storeItems = useMemo(
    () =>
      (storesQuery.data?.stores ?? []).map((store) => ({
        id: store.id,
        primary: `${store.code} · ${store.name}`,
        secondary: [store.region, store.store_type].filter(Boolean).join(' · '),
      })),
    [storesQuery.data],
  )
  const productItems = useMemo(
    () =>
      (productsQuery.data?.products ?? []).map((product) => ({
        id: product.id,
        primary: `${product.sku} · ${product.name}`,
        secondary: product.category ?? undefined,
      })),
    [productsQuery.data],
  )

  const formReady =
    validPair &&
    !!dateRange?.from &&
    !!dateRange?.to &&
    forecastHorizon >= 1 &&
    forecastHorizon <= 90 &&
    selectedModels.length >= 1 &&
    splitConfigErrors(effectiveSplit).length === 0

  // The assembled request — typed but NOT sent in Slice A (the CTA is disabled).
  // `auto_train_winner`/`auto_predict` are pinned false by `assembleRunRequest`.
  // Built defensively so it is valid the moment Slice B wires the mutation.
  const runRequest: ModelSelectionRunRequest | null =
    formReady && dateRange?.from && dateRange?.to
      ? assembleRunRequest({
          storeId: storeId!,
          productId: productId!,
          startDate: format(dateRange.from, 'yyyy-MM-dd'),
          endDate: format(dateRange.to, 'yyyy-MM-dd'),
          forecastHorizon,
          rankingMetric,
          splitConfig: effectiveSplit,
          selectedModels,
        })
      : null

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-3xl font-bold">
          <Trophy className="h-7 w-7" />
          Champion Selector
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Configure a store, product, time period, horizon and candidate models,
          and check whether the pair has enough history to model. Running the
          comparison arrives in a later update.
        </p>
      </div>

      {/* Selection */}
      <Card>
        <CardHeader>
          <CardTitle>1 · Pick a store &amp; product</CardTitle>
          <CardDescription>
            Search by code/SKU or name. The availability check runs automatically
            once a valid pair and horizon are chosen.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div className="space-y-1">
              <span className="text-xs text-muted-foreground">Store</span>
              <SearchableEntitySelect
                items={storeItems}
                value={storeId}
                onChange={setStoreId}
                loading={storesQuery.isLoading}
                placeholder="Pick a store…"
                testId="champion-store-select"
              />
            </div>
            <div className="space-y-1">
              <span className="text-xs text-muted-foreground">Product</span>
              <SearchableEntitySelect
                items={productItems}
                value={productId}
                onChange={setProductId}
                loading={productsQuery.isLoading}
                placeholder="Pick a product…"
                testId="champion-product-select"
              />
            </div>
            <div className="space-y-1">
              <span className="text-xs text-muted-foreground">Time period</span>
              <DateRangePicker value={dateRange} onChange={setDateRange} />
            </div>
            <div className="space-y-1">
              <span className="text-xs text-muted-foreground">
                Forecast horizon (days)
              </span>
              <Input
                type="number"
                min={1}
                max={90}
                value={String(forecastHorizon)}
                data-testid="champion-horizon"
                onChange={(event) =>
                  setForecastHorizon(Number(event.target.value) || 0)
                }
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Availability */}
      <Card>
        <CardHeader>
          <CardTitle>2 · Data availability</CardTitle>
          <CardDescription>
            Whether this pair has enough observed history for a reliable
            comparison, plus the recommended split.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <AvailabilityPanel
            availability={availabilityQuery.data}
            isLoading={validPair && availabilityQuery.isLoading}
            isError={availabilityQuery.isError}
          />
        </CardContent>
      </Card>

      {/* Candidate models */}
      <Card>
        <CardHeader>
          <CardTitle>3 · Candidate models</CardTitle>
          <CardDescription>
            Pick the models to compare (up to 10). The default five are
            pre-selected; opt-in extras are flagged.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {catalogQuery.isError ? (
            <ErrorDisplay
              error={catalogQuery.error}
              title="Could not load the model catalog"
              onRetry={() => catalogQuery.refetch()}
            />
          ) : (
            <CandidateModelPicker
              catalog={catalogQuery.data}
              selected={selectedModels}
              onChange={setEditedModels}
              isLoading={catalogQuery.isLoading}
            />
          )}
        </CardContent>
      </Card>

      {/* Backtest settings */}
      <Card>
        <CardHeader>
          <CardTitle>4 · Backtest settings</CardTitle>
          <CardDescription>
            The ranking metric and cross-validation split. Start with the
            recommended split or fine-tune under Advanced.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <BacktestSettingsForm
            value={effectiveSplit}
            rankingMetric={rankingMetric}
            forecastHorizon={forecastHorizon}
            onChange={setSplitConfig}
            onRankingMetricChange={setRankingMetric}
            recommended={availabilityQuery.data?.recommended_split_config}
          />
        </CardContent>
      </Card>

      {/* Run CTA (disabled until Slice B) */}
      <Card>
        <CardContent className="flex flex-col gap-3 pt-6 sm:flex-row sm:items-center sm:justify-between">
          <div className="text-sm text-muted-foreground">
            {formReady
              ? `Ready to compare ${selectedModels.length} model${
                  selectedModels.length === 1 ? '' : 's'
                }. ${RUN_COMPARISON_PENDING}`
              : 'Pick a store, product, time period, horizon and at least one model to continue.'}
          </div>
          <Button
            type="button"
            disabled
            data-testid="run-comparison-cta"
            // Intentionally inert in Slice A — Slice B wires the POST mutation.
            title={RUN_COMPARISON_PENDING}
          >
            <Trophy className="mr-2 h-4 w-4" />
            Run comparison
          </Button>
        </CardContent>
      </Card>

      {/* Dev-only assurance that a valid request is assembled (not sent). */}
      {runRequest && (
        <p className="sr-only" data-testid="assembled-run-request">
          {JSON.stringify(runRequest)}
        </p>
      )}
    </div>
  )
}
