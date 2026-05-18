import { describe, it, expect } from 'vitest'
import {
  extractForecasts,
  inventoryRequirement,
  joinDemandRows,
  rollups,
  sumWindow,
} from './demand-utils'
import type { InventoryStatusItem, Job, Product } from '@/types/api'

/** Build a completed `predict` Job with the given result payload. */
function makePredictJob(
  jobId: string,
  result: Record<string, unknown> | null,
  runId: string | null = null,
): Job {
  return {
    job_id: jobId,
    job_type: 'predict',
    status: 'completed',
    params: {},
    result,
    error_message: null,
    error_type: null,
    run_id: runId,
    started_at: null,
    completed_at: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }
}

/** A flat forecast series of `count` days, each forecasting `perDay` units. */
function flatForecasts(count: number, perDay: number): Array<{ date: string; forecast: number }> {
  return Array.from({ length: count }, (_, i) => ({
    date: `2026-02-${String(i + 1).padStart(2, '0')}`,
    forecast: perDay,
  }))
}

function makeProduct(id: number, sku: string, name: string): Product {
  return {
    id,
    sku,
    name,
    category: 'Test',
    brand: 'Test',
    base_price: '9.99',
    base_cost: '4.99',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }
}

function makeInventory(
  storeId: number,
  productId: number,
  onHand: number,
  onOrder: number,
): InventoryStatusItem {
  return {
    store_id: storeId,
    product_id: productId,
    date: '2026-01-15',
    on_hand_qty: onHand,
    on_order_qty: onOrder,
    is_stockout: onHand === 0,
  }
}

describe('sumWindow', () => {
  it('sums the first N forecast points', () => {
    expect(sumWindow(flatForecasts(10, 3), 4)).toBe(12)
  })

  it('clamps the window at the array length', () => {
    expect(sumWindow(flatForecasts(5, 2), 30)).toBe(10)
  })

  it('returns 0 for an empty series', () => {
    expect(sumWindow([], 7)).toBe(0)
  })
})

describe('rollups', () => {
  it('returns zeros and a partial month for an empty series', () => {
    const result = rollups([])
    expect(result.tomorrow).toBe(0)
    expect(result.nextWeek).toBe(0)
    expect(result.nextMonth).toBe(0)
    expect(result.nextMonthPartial).toBe(true)
  })

  it('flags nextMonthPartial when the horizon is under 30 days', () => {
    const result = rollups(flatForecasts(14, 5))
    expect(result.tomorrow).toBe(5)
    expect(result.nextWeek).toBe(35)
    expect(result.nextMonth).toBe(70) // only 14 days available
    expect(result.nextMonthPartial).toBe(true)
  })

  it('does not flag a partial month for a 30+ day horizon', () => {
    const result = rollups(flatForecasts(30, 2))
    expect(result.nextMonth).toBe(60)
    expect(result.nextMonthPartial).toBe(false)
  })
})

describe('inventoryRequirement', () => {
  it('returns 0 when on-hand + on-order cover demand', () => {
    expect(inventoryRequirement(40, 30, 20)).toBe(0)
  })

  it('returns the shortfall when stock is insufficient', () => {
    expect(inventoryRequirement(100, 30, 20)).toBe(50)
  })

  it('returns null when on-hand is unknown', () => {
    expect(inventoryRequirement(100, null, null)).toBeNull()
  })

  it('treats a null on-order as zero', () => {
    expect(inventoryRequirement(100, 30, null)).toBe(70)
  })
})

describe('extractForecasts', () => {
  it('extracts a well-formed forecasts array', () => {
    const job = makePredictJob('j1', { forecasts: flatForecasts(3, 7) })
    const forecasts = extractForecasts(job)
    expect(forecasts).not.toBeNull()
    expect(forecasts).toHaveLength(3)
    expect(forecasts?.[0].forecast).toBe(7)
  })

  it('returns null when the result has no forecasts array', () => {
    expect(extractForecasts(makePredictJob('j1', { store_id: 1 }))).toBeNull()
    expect(extractForecasts(makePredictJob('j2', null))).toBeNull()
  })

  it('skips malformed entries', () => {
    const job = makePredictJob('j1', {
      forecasts: [{ date: '2026-02-01', forecast: 5 }, { date: '2026-02-02' }, null],
    })
    expect(extractForecasts(job)).toHaveLength(1)
  })
})

describe('joinDemandRows', () => {
  const products = [makeProduct(10, 'SKU-10', 'Widget'), makeProduct(20, 'SKU-20', 'Gadget')]

  it('skips predict jobs whose result has no forecasts', () => {
    const jobs = [makePredictJob('empty', { store_id: 1, product_id: 10 })]
    expect(joinDemandRows(jobs, products, [], 14)).toHaveLength(0)
  })

  it('builds a row joined to product and inventory', () => {
    const job = makePredictJob('j1', {
      store_id: 1,
      product_id: 10,
      model_type: 'naive',
      horizon: 14,
      forecasts: flatForecasts(14, 5),
    })
    const inventory = [makeInventory(1, 10, 30, 10)]
    const [row] = joinDemandRows([job], products, inventory, 14)
    expect(row.sku).toBe('SKU-10')
    expect(row.productName).toBe('Widget')
    expect(row.tomorrow).toBe(5)
    expect(row.nextWeek).toBe(35)
    expect(row.onHand).toBe(30)
    // leadTimeDemand = 14 * 5 = 70; requirement = 70 - 30 - 10 = 30
    expect(row.inventoryRequirement).toBe(30)
    expect(row.nextMonthPartial).toBe(true)
  })

  it('yields a null requirement when no inventory snapshot exists for the grain', () => {
    const job = makePredictJob('j1', {
      store_id: 9,
      product_id: 10,
      forecasts: flatForecasts(14, 5),
    })
    const [row] = joinDemandRows([job], products, [], 14)
    expect(row.onHand).toBeNull()
    expect(row.onOrder).toBeNull()
    expect(row.inventoryRequirement).toBeNull()
  })

  it('falls back to a #id SKU when the product is unknown', () => {
    const job = makePredictJob('j1', {
      store_id: 1,
      product_id: 999,
      forecasts: flatForecasts(7, 3),
    })
    const [row] = joinDemandRows([job], products, [], 14)
    expect(row.sku).toBe('#999')
    expect(row.productName).toBe('Unknown product')
  })
})
