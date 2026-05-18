import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { subDays } from 'date-fns'
import { ArrowLeft, DollarSign, ShoppingCart, TrendingUp, Users } from 'lucide-react'
import { DateRange } from 'react-day-picker'
import { useProduct } from '@/hooks/use-products'
import { useKPIs } from '@/hooks/use-kpis'
import { useTimeseries } from '@/hooks/use-timeseries'
import { useDrilldowns } from '@/hooks/use-drilldowns'
import { useLifecycleCurve } from '@/hooks/use-lifecycle-curve'
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

export default function ProductDetailPage() {
  const { productId } = useParams()
  const id = Number(productId)
  const validId = !Number.isNaN(id) && id > 0

  const [dateRange, setDateRange] = useState<DateRange | undefined>({
    from: subDays(new Date(), 30),
    to: new Date(),
  })
  const { startDate, endDate } = dateRangeToStrings(dateRange)
  const rangeReady = !!startDate && !!endDate

  const productQuery = useProduct(id, validId)
  const kpiQuery = useKPIs({
    startDate: startDate ?? '',
    endDate: endDate ?? '',
    productId: id,
    enabled: validId && rangeReady,
  })
  const timeseriesQuery = useTimeseries({
    startDate: startDate ?? '',
    endDate: endDate ?? '',
    granularity: 'day',
    productId: id,
    enabled: validId && rangeReady,
  })
  const topStoresQuery = useDrilldowns({
    dimension: 'store',
    startDate: startDate ?? '',
    endDate: endDate ?? '',
    productId: id,
    maxItems: 10,
    enabled: validId && rangeReady,
  })
  const lifecycleQuery = useLifecycleCurve(id, { enabled: validId })

  if (!validId) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Product Detail</h1>
        <ErrorDisplay
          error={new Error(`"${productId}" is not a valid product id.`)}
          title="Invalid product"
        />
      </div>
    )
  }

  if (productQuery.error) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Product Detail</h1>
        <ErrorDisplay error={productQuery.error} onRetry={() => void productQuery.refetch()} />
      </div>
    )
  }

  const product = productQuery.data
  const metrics = kpiQuery.data?.metrics
  const points = timeseriesQuery.data?.points ?? []
  const topStores = topStoresQuery.data?.items ?? []
  const lifecyclePoints = lifecycleQuery.data?.points ?? []

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="space-y-1">
          <Button asChild variant="ghost" size="sm" className="-ml-2 h-7">
            <Link to={ROUTES.EXPLORER.PRODUCTS}>
              <ArrowLeft className="mr-1 h-4 w-4" />
              Back to Products
            </Link>
          </Button>
          <h1 className="text-3xl font-bold">{product?.name ?? 'Product'}</h1>
          {product && (
            <p className="text-sm text-muted-foreground">
              {product.sku}
              {product.category ? ` · ${product.category}` : ''}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <DateRangePicker value={dateRange} onChange={setDateRange} />
          <Button asChild variant="outline">
            <Link to={`${ROUTES.EXPLORER.SALES}?product_id=${id}`}>View in Sales</Link>
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Product profile</CardTitle>
          <CardDescription>Dimension record for this product.</CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div>
              <dt className="text-xs text-muted-foreground">SKU</dt>
              <dd className="font-medium">{product?.sku ?? '-'}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Category</dt>
              <dd className="font-medium">{product?.category ?? '-'}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Brand</dt>
              <dd className="font-medium">{product?.brand ?? '-'}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Base Price</dt>
              <dd className="font-medium">{formatCurrency(product?.base_price)}</dd>
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

      {lifecyclePoints.length > 0 && (
        <TimeSeriesChart
          title="Lifecycle demand curve"
          description="Reference demand multiplier across the product lifecycle."
          data={lifecyclePoints.map((p) => ({
            date: p.date,
            actual: p.multiplier,
          }))}
          showPredicted={false}
        />
      )}

      {topStores.length > 0 ? (
        <RevenueBarChart
          title="Top stores"
          description="Highest-revenue stores selling this product."
          data={topStores.map((item) => ({
            label: item.dimension_value,
            revenue: Number(item.metrics.total_revenue),
          }))}
        />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Top stores</CardTitle>
            <CardDescription>No store sales in the selected period.</CardDescription>
          </CardHeader>
        </Card>
      )}
    </div>
  )
}
