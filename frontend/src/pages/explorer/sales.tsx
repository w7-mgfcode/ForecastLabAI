import { useState } from 'react'
import { format, subDays } from 'date-fns'
import { DateRange } from 'react-day-picker'
import { useDrilldowns } from '@/hooks/use-drilldowns'
import { DateRangePicker } from '@/components/common/date-range-picker'
import { dateRangeToStrings } from '@/lib/date-utils'
import { ErrorDisplay } from '@/components/common/error-display'
import { LoadingState } from '@/components/common/loading-state'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { formatCurrency, formatNumber } from '@/lib/api'
import type { DrilldownDimension } from '@/types/api'

export default function SalesExplorerPage() {
  const [dateRange, setDateRange] = useState<DateRange | undefined>({
    from: subDays(new Date(), 30),
    to: new Date(),
  })
  const [dimension, setDimension] = useState<DrilldownDimension>('store')

  const { startDate, endDate } = dateRangeToStrings(dateRange)

  const { data, isLoading, error, refetch } = useDrilldowns({
    dimension,
    startDate: startDate ?? '',
    endDate: endDate ?? '',
    maxItems: 20,
    enabled: !!startDate && !!endDate,
  })

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Sales Explorer</h1>
        <ErrorDisplay error={error} onRetry={refetch} />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <h1 className="text-3xl font-bold">Sales Explorer</h1>
        <DateRangePicker
          value={dateRange}
          onChange={setDateRange}
          placeholder="Select date range"
        />
      </div>

      <Tabs value={dimension} onValueChange={(v) => setDimension(v as DrilldownDimension)}>
        <TabsList>
          <TabsTrigger value="store">By Store</TabsTrigger>
          <TabsTrigger value="product">By Product</TabsTrigger>
          <TabsTrigger value="category">By Category</TabsTrigger>
          <TabsTrigger value="region">By Region</TabsTrigger>
          <TabsTrigger value="date">By Date</TabsTrigger>
        </TabsList>

        <TabsContent value={dimension} className="mt-6">
          {isLoading ? (
            <LoadingState message="Loading sales data..." />
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>Sales by {dimension.charAt(0).toUpperCase() + dimension.slice(1)}</CardTitle>
                <CardDescription>
                  {data?.total_items ?? 0} items found for{' '}
                  {startDate && format(new Date(startDate), 'MMM d, yyyy')} -{' '}
                  {endDate && format(new Date(endDate), 'MMM d, yyyy')}
                </CardDescription>
              </CardHeader>
              <CardContent>
                {data?.items.length ? (
                  <div className="space-y-3">
                    {data.items.map((item, idx) => (
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
