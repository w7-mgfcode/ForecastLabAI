import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from 'recharts'
import {
  ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from '@/components/ui/chart'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { labelForBucket, sortBuckets } from '@/lib/horizon-bucket-utils'

/**
 * PRP-37 Slice C — per-horizon-bucket bar chart. Sibling to BacktestFoldsChart
 * (the data shape is different — bucket-aggregate vs per-fold — so this is
 * NOT a metricKey toggle on the existing component). Empty state matches the
 * HorizonBucketTable empty state.
 */

export type HorizonBucketChartMetric =
  | 'mae'
  | 'smape'
  | 'wape'
  | 'bias'
  | 'rmse'

interface BacktestHorizonBucketsChartProps {
  bucketed:
    | Record<string, Record<string, number>>
    | null
    | undefined
  metric: HorizonBucketChartMetric
  height?: number
  title?: string
  description?: string
}

const METRIC_COLOR: Record<HorizonBucketChartMetric, string> = {
  mae: 'var(--chart-1)',
  smape: 'var(--chart-2)',
  wape: 'var(--chart-3)',
  bias: 'var(--chart-4)',
  rmse: 'var(--chart-5)',
}

const METRIC_LABEL: Record<HorizonBucketChartMetric, string> = {
  mae: 'MAE',
  smape: 'sMAPE',
  wape: 'WAPE',
  bias: 'Bias',
  rmse: 'RMSE',
}

export function BacktestHorizonBucketsChart({
  bucketed,
  metric,
  height = 240,
  title = 'Metric by horizon bucket',
  description,
}: BacktestHorizonBucketsChartProps) {
  if (!bucketed || Object.keys(bucketed).length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          {description && <CardDescription>{description}</CardDescription>}
        </CardHeader>
        <CardContent>
          <p
            className="text-muted-foreground text-sm"
            data-testid="horizon-buckets-chart-empty"
          >
            No horizon-bucket metrics available.
          </p>
        </CardContent>
      </Card>
    )
  }

  const sortedIds = sortBuckets(Object.keys(bucketed))
  const data = sortedIds.map((id) => ({
    bucket: id,
    label: labelForBucket(id),
    value: bucketed[id]?.[metric] ?? 0,
  }))

  const chartConfig: ChartConfig = {
    value: {
      label: METRIC_LABEL[metric],
      color: METRIC_COLOR[metric],
    },
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>
        <ChartContainer
          config={chartConfig}
          className="w-full"
          style={{ height: `${height}px` }}
          data-testid="horizon-buckets-chart"
        >
          <BarChart data={data} accessibilityLayer>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="label" tickLine={false} axisLine={false} />
            <YAxis tickLine={false} axisLine={false} />
            <ChartTooltip content={<ChartTooltipContent />} />
            <Bar
              dataKey="value"
              name={METRIC_LABEL[metric]}
              fill={METRIC_COLOR[metric]}
              radius={[4, 4, 0, 0]}
            />
          </BarChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
