/**
 * Pure demand-rollup + inventory math for the Demand Planner page.
 *
 * No React, no I/O — every function here is unit-tested in demand-utils.test.ts.
 * The Demand Planner composes these to turn completed `predict` jobs into a
 * multi-SKU demand table.
 */
import type { DemandRow, ForecastPoint, InventoryStatusItem, Job, Product } from '@/types/api'

/** Sum the `forecast` value of the first `days` points (clamped at the array length). */
export function sumWindow(forecasts: { forecast: number }[], days: number): number {
  return forecasts.slice(0, Math.max(0, days)).reduce((sum, point) => sum + point.forecast, 0)
}

/** Tomorrow / next-week / next-month demand rollups for one forecast series. */
export interface DemandRollups {
  tomorrow: number
  nextWeek: number
  nextMonth: number
  /** True when the horizon is shorter than 30 days — nextMonth is a partial sum. */
  nextMonthPartial: boolean
}

/** Roll a daily forecast series up into tomorrow / next-week / next-month totals. */
export function rollups(forecasts: { forecast: number }[]): DemandRollups {
  return {
    tomorrow: forecasts[0]?.forecast ?? 0,
    nextWeek: sumWindow(forecasts, 7),
    nextMonth: sumWindow(forecasts, 30),
    nextMonthPartial: forecasts.length < 30,
  }
}

/**
 * Units to reorder to cover `leadTimeDemand`.
 *
 * Returns 0 when on-hand + on-order already cover the demand, and `null` when
 * stock is unknown (no inventory snapshot for the grain).
 */
export function inventoryRequirement(
  leadTimeDemand: number,
  onHand: number | null,
  onOrder: number | null,
): number | null {
  if (onHand === null) return null
  // Round up: a fractional shortfall still needs a whole extra unit ordered —
  // Math.round would under-order when the fraction is below 0.5.
  return Math.max(0, Math.ceil(leadTimeDemand - onHand - (onOrder ?? 0)))
}

/**
 * Defensively extract a `predict` job's `result.forecasts` array.
 *
 * Job.result is `Record<string, unknown> | null`; a job whose result has no
 * usable forecasts array yields `null` (the caller skips it — never crashes).
 */
export function extractForecasts(job: Job): ForecastPoint[] | null {
  const raw = job.result?.forecasts
  if (!Array.isArray(raw)) return null
  const points: ForecastPoint[] = []
  for (const entry of raw) {
    if (entry && typeof entry === 'object') {
      const record = entry as Record<string, unknown>
      if (typeof record.date === 'string' && typeof record.forecast === 'number') {
        points.push({
          date: record.date,
          forecast: record.forecast,
          lower_bound: typeof record.lower_bound === 'number' ? record.lower_bound : null,
          upper_bound: typeof record.upper_bound === 'number' ? record.upper_bound : null,
        })
      }
    }
  }
  return points
}

/**
 * Join completed `predict` jobs to products + the latest inventory snapshot
 * into Demand Planner table rows.
 *
 * Jobs whose result has no usable forecasts are skipped. A grain with no
 * inventory snapshot still produces a row (onHand/onOrder/requirement null).
 */
export function joinDemandRows(
  predictJobs: Job[],
  products: Product[],
  inventory: InventoryStatusItem[],
  leadTimeDays: number,
): DemandRow[] {
  const productById = new Map(products.map((product) => [product.id, product]))
  // Keep the latest snapshot per grain. The API returns one row per grain, but
  // a naive Map-from-entries would silently keep whichever row is last in the
  // array — pick by `date` so order in the response can never matter.
  const inventoryByGrain = new Map<string, InventoryStatusItem>()
  for (const item of inventory) {
    const key = `${item.store_id}:${item.product_id}`
    const existing = inventoryByGrain.get(key)
    if (!existing || item.date > existing.date) {
      inventoryByGrain.set(key, item)
    }
  }

  const rows: DemandRow[] = []
  for (const job of predictJobs) {
    const forecasts = extractForecasts(job)
    if (!forecasts || forecasts.length === 0) continue

    const result = job.result ?? {}
    const storeId = typeof result.store_id === 'number' ? result.store_id : 0
    const productId = typeof result.product_id === 'number' ? result.product_id : 0
    const modelType = typeof result.model_type === 'string' ? result.model_type : 'unknown'
    const horizon = typeof result.horizon === 'number' ? result.horizon : forecasts.length

    const product = productById.get(productId)
    const inventoryItem = inventoryByGrain.get(`${storeId}:${productId}`)
    const onHand = inventoryItem ? inventoryItem.on_hand_qty : null
    const onOrder = inventoryItem ? inventoryItem.on_order_qty : null

    const seriesRollups = rollups(forecasts)
    const leadTimeDemand = sumWindow(forecasts, leadTimeDays)

    rows.push({
      jobId: job.job_id,
      runId: typeof job.run_id === 'string' ? job.run_id : null,
      storeId,
      productId,
      sku: product?.sku ?? `#${productId}`,
      productName: product?.name ?? 'Unknown product',
      modelType,
      horizon,
      tomorrow: seriesRollups.tomorrow,
      nextWeek: seriesRollups.nextWeek,
      nextMonth: seriesRollups.nextMonth,
      nextMonthPartial: seriesRollups.nextMonthPartial,
      onHand,
      onOrder,
      isStockout: inventoryItem ? inventoryItem.is_stockout : false,
      inventoryRequirement: inventoryRequirement(leadTimeDemand, onHand, onOrder),
      forecasts,
    })
  }
  return rows
}
