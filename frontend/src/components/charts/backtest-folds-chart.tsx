import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Legend, Cell } from 'recharts'
import {
  ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from '@/components/ui/chart'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

interface FoldMetric {
  fold: number
  mae: number
  smape: number
  wape: number
  bias: number
}

interface BacktestFoldsChartProps {
  title: string
  description?: string
  data: FoldMetric[]
  metricKey?: 'mae' | 'smape' | 'wape' | 'bias'
  height?: number
  className?: string
}

const metricColors: Record<string, string> = {
  mae: 'hsl(var(--chart-1))',
  smape: 'hsl(var(--chart-2))',
  wape: 'hsl(var(--chart-3))',
  bias: 'hsl(var(--chart-4))',
}

const metricLabels: Record<string, string> = {
  mae: 'MAE',
  smape: 'sMAPE',
  wape: 'WAPE',
  bias: 'Bias',
}

const chartConfig: ChartConfig = {
  mae: { label: 'MAE', color: metricColors.mae },
  smape: { label: 'sMAPE', color: metricColors.smape },
  wape: { label: 'WAPE', color: metricColors.wape },
  bias: { label: 'Bias', color: metricColors.bias },
}

export function BacktestFoldsChart({
  title,
  description,
  data,
  metricKey = 'mae',
  height = 300,
  className,
}: BacktestFoldsChartProps) {
  const formattedData = data.map((d) => ({
    ...d,
    foldLabel: `Fold ${d.fold}`,
  }))

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>
        <ChartContainer config={chartConfig} className={`h-[${height}px] w-full`}>
          <BarChart data={formattedData} accessibilityLayer>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="foldLabel" tickLine={false} axisLine={false} />
            <YAxis tickLine={false} axisLine={false} />
            <ChartTooltip content={<ChartTooltipContent />} />
            <Legend />
            <Bar
              dataKey={metricKey}
              name={metricLabels[metricKey]}
              radius={[4, 4, 0, 0]}
            >
              {formattedData.map((_, index) => (
                <Cell key={`cell-${index}`} fill={metricColors[metricKey]} />
              ))}
            </Bar>
          </BarChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}

interface MetricsSummaryProps {
  metrics: {
    label: string
    value: number
    unit?: string
    description?: string
  }[]
  className?: string
}

export function MetricsSummary({ metrics, className }: MetricsSummaryProps) {
  return (
    <div className={`grid grid-cols-2 md:grid-cols-4 gap-4 ${className}`}>
      {metrics.map((metric) => (
        <div key={metric.label} className="space-y-1">
          <p className="text-sm font-medium text-muted-foreground">{metric.label}</p>
          <p className="text-2xl font-bold">
            {metric.value.toFixed(2)}
            {metric.unit && <span className="text-sm font-normal ml-1">{metric.unit}</span>}
          </p>
          {metric.description && (
            <p className="text-xs text-muted-foreground">{metric.description}</p>
          )}
        </div>
      ))}
    </div>
  )
}
