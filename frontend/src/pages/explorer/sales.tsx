import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { format, subDays } from 'date-fns'
import { X } from 'lucide-react'
import { DateRange } from 'react-day-picker'
import { useDrilldowns } from '@/hooks/use-drilldowns'
import { useTimeseries } from '@/hooks/use-timeseries'
import { DateRangePicker } from '@/components/common/date-range-picker'
import { ErrorDisplay } from '@/components/common/error-display'
import { LoadingState } from '@/components/common/loading-state'
import { RevenueBarChart } from '@/components/charts/revenue-bar-chart'
import { TimeSeriesChart } from '@/components/charts/time-series-chart'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { dateRangeToStrings, stringsToDateRange } from '@/lib/date-utils'
import { parseEnumParam, parseIdParam } from '@/lib/url-params'
import { formatCurrency, formatNumber } from '@/lib/api'
import type { DrilldownDimension } from '@/types/api'

/** The drilldown dimensions a shareable URL is allowed to select. */
const DRILLDOWN_DIMENSIONS: readonly DrilldownDimension[] = [
  'store',
  'product',
  'category',
  'region',
  'date',
]

export default function SalesExplorerPage() {
  const [searchParams, setSearchParams] = useSearchParams()

  // dimension + cross-filter state live in the URL so the view is shareable.
  // A hand-edited URL can carry an unknown dimension or a NaN id — validate
  // both before they reach the drilldown/timeseries hooks.
  const dimension = parseEnumParam(searchParams.get('dimension'), DRILLDOWN_DIMENSIONS) ?? 'store'
  const storeId = parseIdParam(searchParams.get('store_id'))
  const productId = parseIdParam(searchParams.get('product_id'))

  const startParam = searchParams.get('start_date')
  const endParam = searchParams.get('end_date')
  const [dateRange, setDateRange] = useState<DateRange | undefined>(() =>
    startParam
      ? stringsToDateRange(startParam, endParam ?? undefined)
      : { from: subDays(new Date(), 30), to: new Date() }
  )

  const { startDate, endDate } = dateRangeToStrings(dateRange)
  const rangeReady = !!startDate && !!endDate

  function updateParams(updates: Record<string, string | undefined>) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      for (const [key, value] of Object.entries(updates)) {
        if (value === undefined || value === '') next.delete(key)
        else next.set(key, value)
      }
      return next
    })
  }

  const handleDateChange = (range: DateRange | undefined) => {
    setDateRange(range)
    const { startDate: nextStart, endDate: nextEnd } = dateRangeToStrings(range)
    updateParams({ start_date: nextStart, end_date: nextEnd })
  }

  const drilldown = useDrilldowns({
    dimension,
    startDate: startDate ?? '',
    endDate: endDate ?? '',
    storeId,
    productId,
    maxItems: 20,
    enabled: rangeReady,
  })

  const timeseries = useTimeseries({
    startDate: startDate ?? '',
    endDate: endDate ?? '',
    granularity: 'day',
    storeId,
    productId,
    enabled: rangeReady,
  })

  if (drilldown.error) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Sales Explorer</h1>
        <ErrorDisplay error={drilldown.error} onRetry={() => void drilldown.refetch()} />
      </div>
    )
  }

  const items = drilldown.data?.items ?? []
  const points = timeseries.data?.points ?? []
  const dimensionLabel = dimension.charAt(0).toUpperCase() + dimension.slice(1)

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <h1 className="text-3xl font-bold">Sales Explorer</h1>
        <DateRangePicker value={dateRange} onChange={handleDateChange} />
      </div>

      {(storeId !== undefined || productId !== undefined) && (
        <div className="flex flex-wrap gap-2">
          {storeId !== undefined && (
            <Badge variant="secondary" className="gap-1">
              Filtered to store #{storeId}
              <button
                type="button"
                aria-label="Clear store filter"
                onClick={() => updateParams({ store_id: undefined })}
                className="ml-1 rounded-full hover:text-foreground"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          )}
          {productId !== undefined && (
            <Badge variant="secondary" className="gap-1">
              Filtered to product #{productId}
              <button
                type="button"
                aria-label="Clear product filter"
                onClick={() => updateParams({ product_id: undefined })}
                className="ml-1 rounded-full hover:text-foreground"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          )}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {items.length > 0 ? (
          <RevenueBarChart
            title={`Revenue by ${dimensionLabel}`}
            description="Top contributors for the selected period."
            data={items.map((item) => ({
              label: item.dimension_value,
              revenue: Number(item.metrics.total_revenue),
            }))}
          />
        ) : (
          <Card>
            <CardHeader>
              <CardTitle>Revenue by {dimensionLabel}</CardTitle>
              <CardDescription>No sales data for the selected period.</CardDescription>
            </CardHeader>
          </Card>
        )}
        {points.length > 0 ? (
          <TimeSeriesChart
            title="Revenue over time"
            description="Daily revenue for the selected period."
            data={points.map((p) => ({
              date: p.period,
              actual: Number(p.metrics.total_revenue),
            }))}
            showPredicted={false}
          />
        ) : (
          <Card>
            <CardHeader>
              <CardTitle>Revenue over time</CardTitle>
              <CardDescription>No sales data for the selected period.</CardDescription>
            </CardHeader>
          </Card>
        )}
      </div>

      <Tabs value={dimension} onValueChange={(v) => updateParams({ dimension: v })}>
        <TabsList>
          <TabsTrigger value="store">By Store</TabsTrigger>
          <TabsTrigger value="product">By Product</TabsTrigger>
          <TabsTrigger value="category">By Category</TabsTrigger>
          <TabsTrigger value="region">By Region</TabsTrigger>
          <TabsTrigger value="date">By Date</TabsTrigger>
        </TabsList>

        <TabsContent value={dimension} className="mt-6">
          {drilldown.isLoading ? (
            <LoadingState message="Loading sales data..." />
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>Sales by {dimensionLabel}</CardTitle>
                <CardDescription>
                  {drilldown.data?.total_items ?? 0} items found for{' '}
                  {startDate && format(new Date(startDate), 'MMM d, yyyy')} -{' '}
                  {endDate && format(new Date(endDate), 'MMM d, yyyy')}
                </CardDescription>
              </CardHeader>
              <CardContent>
                {items.length ? (
                  <div className="space-y-3">
                    {items.map((item, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between py-2 border-b last:border-0"
                      >
                        <div className="flex items-center gap-3">
                          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-muted text-xs font-medium">
                            {item.rank}
                          </span>
                          <div>
                            <p className="font-medium">{item.dimension_value}</p>
                            <p className="text-xs text-muted-foreground">
                              {formatNumber(item.metrics.total_units)} units |{' '}
                              {formatNumber(item.metrics.total_transactions)} txns
                            </p>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="font-medium">
                            {formatCurrency(item.metrics.total_revenue)}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {item.revenue_share_pct}% share
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground text-center py-8">
                    No sales data available for the selected period.
                  </p>
                )}
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
