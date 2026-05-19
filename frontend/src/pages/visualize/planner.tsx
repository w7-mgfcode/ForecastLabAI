import { useState } from 'react'
import { AlertTriangle, BarChart3, Download, Loader2, Play, Save, Trash2 } from 'lucide-react'
import { useJob } from '@/hooks/use-jobs'
import {
  useCompareScenarios,
  useCreateScenario,
  useDeleteScenario,
  useScenario,
  useScenarios,
  useSimulateScenario,
} from '@/hooks/use-scenarios'
import { MultiSeriesChart } from '@/components/charts/multi-series-chart'
import { TimeSeriesChart } from '@/components/charts/time-series-chart'
import { JobPicker } from '@/components/common/job-picker'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { StatusBadge } from '@/components/common/status-badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { downloadCsv, toCsv } from '@/lib/csv-export'
import { formatCurrency, formatNumber, getErrorMessage } from '@/lib/api'
import {
  buildMultiSeries,
  coverageLabel,
  coverageVariant,
  deltaCsvColumns,
  formatDelta,
  mergeComparisonSeries,
  methodLabel,
} from '@/lib/scenario-utils'
import type {
  MultiScenarioComparison,
  PromotionAssumption,
  ScenarioAssumptions,
  ScenarioComparison,
} from '@/types/api'

/** Horizon presets (days) for a simulation run. */
const HORIZON_OPTIONS = [7, 14, 30, 60, 90]
/** Promotion mechanics offered on the assumption form. */
const PROMOTION_KINDS: PromotionAssumption['kind'][] = ['pct_off', 'bogo', 'bundle', 'markdown']
/** Lifecycle stages offered on the assumption form. */
const LIFECYCLE_STAGES = ['launch', 'growth', 'maturity', 'decline'] as const

/** A headline metric tile for the results panel. */
function KpiTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-bold">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </div>
  )
}

export default function WhatIfPlannerPage() {
  // -- Baseline selection ------------------------------------------------
  const [selectedJobId, setSelectedJobId] = useState('')
  const [horizon, setHorizon] = useState(14)
  const { data: job } = useJob(selectedJobId, !!selectedJobId)
  // A predict job's params.run_id is the baseline model artifact key.
  const baselineRunId = typeof job?.params?.run_id === 'string' ? job.params.run_id : null

  // -- Assumption form state ---------------------------------------------
  const [priceEnabled, setPriceEnabled] = useState(false)
  const [priceChangePct, setPriceChangePct] = useState(-15)
  const [priceStart, setPriceStart] = useState('')
  const [priceEnd, setPriceEnd] = useState('')

  const [promoEnabled, setPromoEnabled] = useState(false)
  const [promoKind, setPromoKind] = useState<PromotionAssumption['kind']>('pct_off')
  const [promoStart, setPromoStart] = useState('')
  const [promoEnd, setPromoEnd] = useState('')

  const [holidayEnabled, setHolidayEnabled] = useState(false)
  const [holidayDates, setHolidayDates] = useState('')

  const [inventoryEnabled, setInventoryEnabled] = useState(false)
  const [onHandUnits, setOnHandUnits] = useState(0)

  const [lifecycleEnabled, setLifecycleEnabled] = useState(false)
  const [lifecycleStage, setLifecycleStage] =
    useState<(typeof LIFECYCLE_STAGES)[number]>('maturity')

  // -- Results / persistence state ---------------------------------------
  const [simulated, setSimulated] = useState<ScenarioComparison | null>(null)
  const [planName, setPlanName] = useState('')
  const [runError, setRunError] = useState<string | null>(null)
  const [reloadId, setReloadId] = useState('')

  // -- Multi-scenario comparison state -----------------------------------
  const [selectedPlanIds, setSelectedPlanIds] = useState<Set<string>>(new Set())
  const [multiComparison, setMultiComparison] = useState<MultiScenarioComparison | null>(null)
  const [compareError, setCompareError] = useState<string | null>(null)

  const simulate = useSimulateScenario()
  const createScenario = useCreateScenario()
  const deleteScenario = useDeleteScenario()
  const compareScenarios = useCompareScenarios()
  const scenariosQuery = useScenarios()
  const reloadedPlan = useScenario(reloadId, !!reloadId)

  // The comparison on screen is either a fresh simulation result or, when a
  // saved plan has been reloaded, that plan's embedded snapshot. Deriving it
  // (rather than copying into state inside an effect) keeps the render pure.
  const comparison: ScenarioComparison | null = reloadId
    ? (reloadedPlan.data?.comparison ?? null)
    : simulated

  /** Assemble the ScenarioAssumptions payload from the enabled form sections. */
  function buildAssumptions(): ScenarioAssumptions {
    const assumptions: ScenarioAssumptions = {}
    if (priceEnabled) {
      assumptions.price = {
        change_pct: priceChangePct / 100,
        start_date: priceStart,
        end_date: priceEnd,
      }
    }
    if (promoEnabled) {
      assumptions.promotion = { kind: promoKind, start_date: promoStart, end_date: promoEnd }
    }
    if (holidayEnabled) {
      const dates = holidayDates
        .split(',')
        .map((value) => value.trim())
        .filter(Boolean)
      if (dates.length > 0) assumptions.holiday = { dates }
    }
    if (inventoryEnabled) {
      assumptions.inventory = { on_hand_units: onHandUnits }
    }
    if (lifecycleEnabled) {
      assumptions.lifecycle = { stage: lifecycleStage }
    }
    return assumptions
  }

  async function handleRun() {
    if (!baselineRunId) return
    setRunError(null)
    setReloadId('')
    try {
      const result = await simulate.mutateAsync({
        run_id: baselineRunId,
        horizon,
        assumptions: buildAssumptions(),
      })
      setSimulated(result)
    } catch (caught) {
      setRunError(getErrorMessage(caught))
      setSimulated(null)
    }
  }

  async function handleSave() {
    if (!baselineRunId || !planName.trim()) return
    setRunError(null)
    try {
      await createScenario.mutateAsync({
        name: planName.trim(),
        run_id: baselineRunId,
        horizon,
        assumptions: buildAssumptions(),
      })
      setPlanName('')
    } catch (caught) {
      setRunError(getErrorMessage(caught))
    }
  }

  function handleExport() {
    if (!comparison) return
    downloadCsv('scenario-deltas.csv', toCsv(comparison.points, deltaCsvColumns))
  }

  /** Toggle a saved plan in the multi-scenario comparison selection. */
  function togglePlanSelection(scenarioId: string) {
    setSelectedPlanIds((current) => {
      const next = new Set(current)
      if (next.has(scenarioId)) next.delete(scenarioId)
      else next.add(scenarioId)
      return next
    })
  }

  async function handleCompare() {
    if (selectedPlanIds.size < 2) return
    setCompareError(null)
    try {
      const result = await compareScenarios.mutateAsync({
        scenario_ids: [...selectedPlanIds],
        rank_by: 'revenue_delta',
      })
      setMultiComparison(result)
    } catch (caught) {
      setCompareError(getErrorMessage(caught))
      setMultiComparison(null)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">What-If Planner</h1>
        <p className="text-sm text-muted-foreground">
          Take an existing forecast, apply future assumptions — a price change, a promotion,
          holidays, a stock cap — and see the demand and revenue impact before committing.
        </p>
      </div>

      {/* Heuristic disclaimer — always visible, prominent. */}
      <Card className="border-warning/60 bg-warning/10">
        <CardContent className="flex gap-3 pt-6">
          <AlertTriangle className="h-5 w-5 shrink-0 text-warning" />
          <div className="text-sm">
            <p className="font-semibold">Scenario estimates — directional planning signals</p>
            <p className="text-muted-foreground">
              A baseline forecaster yields a heuristic estimate (fixed adjustment factors); a
              regression baseline is genuinely re-forecast through the model. Either way, treat
              the demand and revenue deltas as planning signals, not precise predictions — each
              result states the method that produced it.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Baseline picker */}
      <Card>
        <CardHeader>
          <CardTitle>1. Pick a baseline</CardTitle>
          <CardDescription>
            Choose a completed prediction job — its model is the baseline this scenario adjusts.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <JobPicker
            jobType="predict"
            selectedJobId={selectedJobId}
            onSelect={setSelectedJobId}
            autoSelectLatest
          />
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
          </div>
          {selectedJobId && !baselineRunId && (
            <p className="text-sm text-muted-foreground">
              The selected job has no model artifact — pick a completed predict job.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Assumptions form */}
      <Card>
        <CardHeader>
          <CardTitle>2. Define assumptions</CardTitle>
          <CardDescription>
            Every assumption is optional. Leave them all off for a no-change baseline.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {/* Price */}
          <div className="space-y-2">
            <label className="flex items-center gap-2 text-sm font-medium">
              <Checkbox
                checked={priceEnabled}
                onCheckedChange={(checked) => setPriceEnabled(checked === true)}
              />
              Price change
            </label>
            {priceEnabled && (
              <div className="flex flex-wrap items-end gap-3 pl-6">
                <div className="space-y-1">
                  <span className="text-xs text-muted-foreground">Change %</span>
                  <Input
                    type="number"
                    className="w-[120px]"
                    value={priceChangePct}
                    onChange={(event) => setPriceChangePct(Number(event.target.value))}
                  />
                </div>
                <div className="space-y-1">
                  <span className="text-xs text-muted-foreground">From</span>
                  <Input
                    type="date"
                    className="w-[170px]"
                    value={priceStart}
                    onChange={(event) => setPriceStart(event.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <span className="text-xs text-muted-foreground">To</span>
                  <Input
                    type="date"
                    className="w-[170px]"
                    value={priceEnd}
                    onChange={(event) => setPriceEnd(event.target.value)}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Promotion */}
          <div className="space-y-2">
            <label className="flex items-center gap-2 text-sm font-medium">
              <Checkbox
                checked={promoEnabled}
                onCheckedChange={(checked) => setPromoEnabled(checked === true)}
              />
              Promotion
            </label>
            {promoEnabled && (
              <div className="flex flex-wrap items-end gap-3 pl-6">
                <div className="space-y-1">
                  <span className="text-xs text-muted-foreground">Kind</span>
                  <Select
                    value={promoKind}
                    onValueChange={(value) => setPromoKind(value as PromotionAssumption['kind'])}
                  >
                    <SelectTrigger className="w-[150px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {PROMOTION_KINDS.map((kind) => (
                        <SelectItem key={kind} value={kind}>
                          {kind}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <span className="text-xs text-muted-foreground">From</span>
                  <Input
                    type="date"
                    className="w-[170px]"
                    value={promoStart}
                    onChange={(event) => setPromoStart(event.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <span className="text-xs text-muted-foreground">To</span>
                  <Input
                    type="date"
                    className="w-[170px]"
                    value={promoEnd}
                    onChange={(event) => setPromoEnd(event.target.value)}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Holiday */}
          <div className="space-y-2">
            <label className="flex items-center gap-2 text-sm font-medium">
              <Checkbox
                checked={holidayEnabled}
                onCheckedChange={(checked) => setHolidayEnabled(checked === true)}
              />
              Holiday / event days
            </label>
            {holidayEnabled && (
              <div className="space-y-1 pl-6">
                <span className="text-xs text-muted-foreground">
                  Comma-separated dates (YYYY-MM-DD)
                </span>
                <Input
                  className="max-w-md"
                  placeholder="2026-07-04, 2026-07-05"
                  value={holidayDates}
                  onChange={(event) => setHolidayDates(event.target.value)}
                />
              </div>
            )}
          </div>

          {/* Inventory */}
          <div className="space-y-2">
            <label className="flex items-center gap-2 text-sm font-medium">
              <Checkbox
                checked={inventoryEnabled}
                onCheckedChange={(checked) => setInventoryEnabled(checked === true)}
              />
              Inventory cap
            </label>
            {inventoryEnabled && (
              <div className="space-y-1 pl-6">
                <span className="text-xs text-muted-foreground">On-hand units</span>
                <Input
                  type="number"
                  className="w-[160px]"
                  value={onHandUnits}
                  onChange={(event) => setOnHandUnits(Number(event.target.value))}
                />
              </div>
            )}
          </div>

          {/* Lifecycle */}
          <div className="space-y-2">
            <label className="flex items-center gap-2 text-sm font-medium">
              <Checkbox
                checked={lifecycleEnabled}
                onCheckedChange={(checked) => setLifecycleEnabled(checked === true)}
              />
              Lifecycle stage
            </label>
            {lifecycleEnabled && (
              <div className="space-y-1 pl-6">
                <span className="text-xs text-muted-foreground">Stage</span>
                <Select
                  value={lifecycleStage}
                  onValueChange={(value) =>
                    setLifecycleStage(value as (typeof LIFECYCLE_STAGES)[number])
                  }
                >
                  <SelectTrigger className="w-[160px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {LIFECYCLE_STAGES.map((stage) => (
                      <SelectItem key={stage} value={stage}>
                        {stage}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-3 border-t pt-4">
            <Button onClick={handleRun} disabled={!baselineRunId || simulate.isPending}>
              {simulate.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Play className="mr-2 h-4 w-4" />
              )}
              Run simulation
            </Button>
            {runError && <p className="text-sm text-destructive">{runError}</p>}
          </div>
        </CardContent>
      </Card>

      {/* Results */}
      {comparison && (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Scenario impact</CardTitle>
              <CardDescription>
                {comparison.model_type} model · store {comparison.store_id} · product{' '}
                {comparison.product_id} · {comparison.horizon}-day horizon ·{' '}
                {methodLabel(comparison.method)} estimate
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <KpiTile
                  label="Units delta"
                  value={formatDelta(comparison.units_delta)}
                  hint={`${formatDelta(comparison.units_delta_pct)}% vs baseline`}
                />
                <KpiTile
                  label="Revenue delta"
                  value={formatCurrency(comparison.revenue_delta)}
                  hint={`unit price ${formatCurrency(comparison.unit_price_used)}`}
                />
                <KpiTile
                  label="Scenario units"
                  value={formatNumber(comparison.scenario_total_units)}
                  hint={`baseline ${formatNumber(comparison.baseline_total_units)}`}
                />
                <div className="rounded-lg border p-4">
                  <p className="text-xs text-muted-foreground">Coverage</p>
                  <div className="mt-2">
                    <StatusBadge variant={coverageVariant(comparison.coverage_verdict)}>
                      {coverageLabel(comparison.coverage_verdict)}
                    </StatusBadge>
                  </div>
                </div>
              </div>

              <TimeSeriesChart
                title="Baseline vs. scenario demand"
                description={`${comparison.points.length}-day comparison`}
                data={mergeComparisonSeries(comparison.points)}
                actualKey="baseline"
                predictedKey="scenario"
                showActual
                showPredicted
              />

              <p className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
                {comparison.disclaimer}
              </p>
            </CardContent>
          </Card>

          {/* Per-day delta table */}
          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <CardTitle>Per-day deltas</CardTitle>
                  <CardDescription>Daily baseline, scenario, and applied factor.</CardDescription>
                </div>
                <Button variant="outline" size="sm" onClick={handleExport}>
                  <Download className="mr-2 h-4 w-4" />
                  Export CSV
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead>
                    <TableHead className="text-right">Baseline</TableHead>
                    <TableHead className="text-right">Scenario</TableHead>
                    <TableHead className="text-right">Delta</TableHead>
                    <TableHead className="text-right">Factor</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {comparison.points.map((point) => (
                    <TableRow key={point.date}>
                      <TableCell className="font-mono text-xs">{point.date}</TableCell>
                      <TableCell className="text-right">{formatNumber(point.baseline, 1)}</TableCell>
                      <TableCell className="text-right">{formatNumber(point.scenario, 1)}</TableCell>
                      <TableCell className="text-right">{formatDelta(point.delta)}</TableCell>
                      <TableCell className="text-right">
                        {point.applied_factor.toFixed(2)}×
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {/* Save as plan */}
          <Card>
            <CardHeader>
              <CardTitle>Save this scenario</CardTitle>
              <CardDescription>
                Persist the assumptions and the comparison snapshot as a named plan.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap items-end gap-3">
                <div className="space-y-1">
                  <span className="text-xs text-muted-foreground">Plan name</span>
                  <Input
                    className="w-[280px]"
                    placeholder="e.g. Summer price cut"
                    value={planName}
                    onChange={(event) => setPlanName(event.target.value)}
                  />
                </div>
                <Button
                  onClick={handleSave}
                  disabled={!baselineRunId || !planName.trim() || createScenario.isPending}
                >
                  {createScenario.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="mr-2 h-4 w-4" />
                  )}
                  Save as plan
                </Button>
              </div>
            </CardContent>
          </Card>
        </>
      )}

      {/* Saved plans */}
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>Saved plans</CardTitle>
              <CardDescription>
                Reload a plan to re-render its comparison, or select 2-5 plans to
                compare them side by side.
              </CardDescription>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={handleCompare}
              disabled={selectedPlanIds.size < 2 || compareScenarios.isPending}
            >
              {compareScenarios.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <BarChart3 className="mr-2 h-4 w-4" />
              )}
              Compare selected ({selectedPlanIds.size})
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {compareError && <p className="mb-3 text-sm text-destructive">{compareError}</p>}
          {scenariosQuery.data && scenariosQuery.data.scenarios.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10" />
                  <TableHead>Name</TableHead>
                  <TableHead>Tags</TableHead>
                  <TableHead className="text-right">Units delta</TableHead>
                  <TableHead className="text-right">Revenue delta</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {scenariosQuery.data.scenarios.map((plan) => {
                  const selected = selectedPlanIds.has(plan.scenario_id)
                  return (
                    <TableRow key={plan.scenario_id}>
                      <TableCell>
                        <Checkbox
                          checked={selected}
                          disabled={!selected && selectedPlanIds.size >= 5}
                          onCheckedChange={() => togglePlanSelection(plan.scenario_id)}
                          aria-label={`Select ${plan.name}`}
                        />
                      </TableCell>
                      <TableCell className="font-medium">{plan.name}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {plan.tags.length > 0 ? plan.tags.join(', ') : '—'}
                      </TableCell>
                      <TableCell className="text-right">
                        {formatDelta(plan.units_delta)}
                      </TableCell>
                      <TableCell className="text-right">
                        {formatCurrency(plan.revenue_delta)}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setReloadId(plan.scenario_id)}
                          >
                            Reload
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => deleteScenario.mutate(plan.scenario_id)}
                            disabled={deleteScenario.isPending}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          ) : (
            <p className="text-sm text-muted-foreground">
              No saved plans yet. Run a simulation and save it above.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Multi-scenario comparison result */}
      {multiComparison && (
        <Card>
          <CardHeader>
            <CardTitle>Scenario comparison</CardTitle>
            <CardDescription>
              {multiComparison.scenarios.length} plans ranked by{' '}
              {multiComparison.rank_by === 'revenue_delta' ? 'revenue delta' : 'units delta'}.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-14 text-right">Rank</TableHead>
                  <TableHead>Plan</TableHead>
                  <TableHead className="text-right">Units delta</TableHead>
                  <TableHead className="text-right">Revenue delta</TableHead>
                  <TableHead>Coverage</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {multiComparison.scenarios.map((row) => (
                  <TableRow key={row.scenario_id}>
                    <TableCell className="text-right font-mono">{row.rank}</TableCell>
                    <TableCell className="font-medium">{row.name}</TableCell>
                    <TableCell className="text-right">{formatDelta(row.units_delta)}</TableCell>
                    <TableCell className="text-right">
                      {formatCurrency(row.revenue_delta)}
                    </TableCell>
                    <TableCell>
                      <StatusBadge variant={coverageVariant(row.coverage_verdict)}>
                        {coverageLabel(row.coverage_verdict)}
                      </StatusBadge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <MultiSeriesChart
              title="Baseline vs. scenarios"
              description="Demand per day — the shared baseline plus every compared scenario"
              data={multiComparison.chart_series}
              series={buildMultiSeries(multiComparison)}
            />
          </CardContent>
        </Card>
      )}
    </div>
  )
}
