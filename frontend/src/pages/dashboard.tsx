import { useState } from 'react'
import { subDays } from 'date-fns'
import { DollarSign, ShoppingCart, TrendingUp, Users } from 'lucide-react'
import { DateRange } from 'react-day-picker'
import { useKPIs } from '@/hooks/use-kpis'
import { useDrilldowns } from '@/hooks/use-drilldowns'
import { KPICard } from '@/components/charts/kpi-card'
import { DateRangePicker } from '@/components/common/date-range-picker'
import { dateRangeToStrings } from '@/lib/date-utils'
import { ErrorDisplay } from '@/components/common/error-display'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { formatCurrency, formatNumber } from '@/lib/api'

export default function DashboardPage() {
  const [dateRange, setDateRange] = useState<DateRange | undefined>({
    from: subDays(new Date(), 30),
    to: new Date(),
  })

  const { startDate, endDate } = dateRangeToStrings(dateRange)

  const {
    data: kpiData,
    isLoading: kpisLoading,
    error: kpisError,
    refetch: refetchKPIs,
  } = useKPIs({
    startDate: startDate ?? '',
    endDate: endDate ?? '',
    enabled: !!startDate && !!endDate,
  })

  const { data: topStores, isLoading: storesLoading } = useDrilldowns({
    dimension: 'store',
    startDate: startDate ?? '',
    endDate: endDate ?? '',
    maxItems: 5,
    enabled: !!startDate && !!endDate,
  })

  const { data: topProducts, isLoading: productsLoading } = useDrilldowns({
    dimension: 'product',
    startDate: startDate ?? '',
    endDate: endDate ?? '',
    maxItems: 5,
    enabled: !!startDate && !!endDate,
  })

  if (kpisError) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Dashboard</h1>
        <ErrorDisplay error={kpisError} onRetry={refetchKPIs} />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <h1 className="text-3xl font-bold">Dashboard</h1>
        <DateRangePicker
          value={dateRange}
          onChange={setDateRange}
          placeholder="Select date range"
        />
      </div>

      {/* KPI Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <KPICard
          title="Total Revenue"
          value={formatCurrency(kpiData?.metrics.total_revenue)}
          icon={DollarSign}
          isLoading={kpisLoading}
        />
        <KPICard
          title="Units Sold"
          value={formatNumber(kpiData?.metrics.total_units)}
          icon={ShoppingCart}
          isLoading={kpisLoading}
        />
        <KPICard
          title="Transactions"
          value={formatNumber(kpiData?.metrics.total_transactions)}
          icon={TrendingUp}
          isLoading={kpisLoading}
        />
        <KPICard
          title="Avg Basket Value"
          value={formatCurrency(kpiData?.metrics.avg_basket_value)}
          icon={Users}
          isLoading={kpisLoading}
        />
      </div>

      {/* Top Performers */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Top Stores</CardTitle>
            <CardDescription>By revenue in selected period</CardDescription>
          </CardHeader>
          <CardContent>
            {storesLoading ? (
              <p className="text-sm text-muted-foreground">Loading...</p>
            ) : topStores?.items.length ? (
              <div className="space-y-3">
                {topStores.items.map((store, idx) => (
                  <div key={idx} className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-muted text-xs font-medium">
                        {store.rank}
                      </span>
                      <span className="text-sm font-medium">{store.dimension_value}</span>
                    </div>
                    <span className="text-sm text-muted-foreground">
                      {formatCurrency(store.metrics.total_revenue)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No data available</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Top Products</CardTitle>
            <CardDescription>By revenue in selected period</CardDescription>
          </CardHeader>
          <CardContent>
            {productsLoading ? (
              <p className="text-sm text-muted-foreground">Loading...</p>
            ) : topProducts?.items.length ? (
              <div className="space-y-3">
                {topProducts.items.map((product, idx) => (
                  <div key={idx} className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-muted text-xs font-medium">
                        {product.rank}
                      </span>
                      <span className="text-sm font-medium">{product.dimension_value}</span>
                    </div>
                    <span className="text-sm text-muted-foreground">
                      {formatCurrency(product.metrics.total_revenue)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No data available</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
