import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { subDays } from 'date-fns'
import { ArrowLeft, DollarSign, ShoppingCart, TrendingUp, Users } from 'lucide-react'
import { DateRange } from 'react-day-picker'
import { useStore } from '@/hooks/use-stores'
import { useKPIs } from '@/hooks/use-kpis'
import { useTimeseries } from '@/hooks/use-timeseries'
import { useDrilldowns } from '@/hooks/use-drilldowns'
import { KPICard } from '@/components/charts/kpi-card'
import { TimeSeriesChart } from '@/components/charts/time-series-chart'
import { RevenueBarChart } from '@/components/charts/revenue-bar-chart'
import { DateRangePicker } from '@/components/common/date-range-picker'
import { ErrorDisplay } from '@/components/common/error-display'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { dateRangeToStrings } from '@/lib/date-utils'
import { formatCurrency, formatNumber } from '@/lib/api'
import { ROUTES } from '@/lib/constants'

export default function StoreDetailPage() {
  const { storeId } = useParams()
  const id = Number(storeId)
  const validId = !Number.isNaN(id) && id > 0

  const [dateRange, setDateRange] = useState<DateRange | undefined>({
    from: subDays(new Date(), 30),
    to: new Date(),
  })
  const { startDate, endDate } = dateRangeToStrings(dateRange)
  const rangeReady = !!startDate && !!endDate

  const storeQuery = useStore(id, validId)
  const kpiQuery = useKPIs({
    startDate: startDate ?? '',
    endDate: endDate ?? '',
    storeId: id,
    enabled: validId && rangeReady,
  })
  const timeseriesQuery = useTimeseries({
    startDate: startDate ?? '',
    endDate: endDate ?? '',
    granularity: 'day',
    storeId: id,
    enabled: validId && rangeReady,
  })
  const topProductsQuery = useDrilldowns({
    dimension: 'product',
    startDate: startDate ?? '',
    endDate: endDate ?? '',
    storeId: id,
    maxItems: 10,
    enabled: validId && rangeReady,
  })

  if (!validId) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Store Detail</h1>
        <ErrorDisplay
          error={new Error(`"${storeId}" is not a valid store id.`)}
          title="Invalid store"
        />
      </div>
    )
  }

  if (storeQuery.error) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Store Detail</h1>
        <ErrorDisplay error={storeQuery.error} onRetry={() => void storeQuery.refetch()} />
      </div>
    )
  }

  const store = storeQuery.data
  const metrics = kpiQuery.data?.metrics
  const points = timeseriesQuery.data?.points ?? []
  const topProducts = topProductsQuery.data?.items ?? []

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="space-y-1">
          <Button asChild variant="ghost" size="sm" className="-ml-2 h-7">
            <Link to={ROUTES.EXPLORER.STORES}>
              <ArrowLeft className="mr-1 h-4 w-4" />
              Back to Stores
            </Link>
          </Button>
          <h1 className="text-3xl font-bold">{store?.name ?? 'Store'}</h1>
          {store && (
            <p className="text-sm text-muted-foreground">
              {store.code}
              {store.region ? ` · ${store.region}` : ''}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <DateRangePicker value={dateRange} onChange={setDateRange} />
          <Button asChild variant="outline">
            <Link to={`${ROUTES.EXPLORER.SALES}?store_id=${id}`}>View in Sales</Link>
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Store profile</CardTitle>
          <CardDescription>Dimension record for this store.</CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div>
              <dt className="text-xs text-muted-foreground">Code</dt>
              <dd className="font-medium">{store?.code ?? '-'}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Region</dt>
              <dd className="font-medium">{store?.region ?? '-'}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">City</dt>
              <dd className="font-medium">{store?.city ?? '-'}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Type</dt>
              <dd className="font-medium">{store?.store_type ?? '-'}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <KPICard
          title="Total Revenue"
          value={formatCurrency(metrics?.total_revenue)}
          icon={DollarSign}
          isLoading={kpiQuery.isLoading}
        />
        <KPICard
          title="Units Sold"
          value={formatNumber(metrics?.total_units)}
          icon={ShoppingCart}
          isLoading={kpiQuery.isLoading}
        />
        <KPICard
          title="Transactions"
          value={formatNumber(metrics?.total_transactions)}
          icon={TrendingUp}
          isLoading={kpiQuery.isLoading}
        />
        <KPICard
          title="Avg Basket Value"
          value={formatCurrency(metrics?.avg_basket_value)}
          icon={Users}
          isLoading={kpiQuery.isLoading}
        />
      </div>

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
            <CardDescription>No sales in the selected period.</CardDescription>
          </CardHeader>
        </Card>
      )}

      {topProducts.length > 0 ? (
        <RevenueBarChart
          title="Top products"
          description="Highest-revenue products sold at this store."
          data={topProducts.map((item) => ({
            label: item.dimension_value,
            revenue: Number(item.metrics.total_revenue),
          }))}
        />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Top products</CardTitle>
            <CardDescription>No product sales in the selected period.</CardDescription>
          </CardHeader>
        </Card>
      )}
    </div>
  )
}
