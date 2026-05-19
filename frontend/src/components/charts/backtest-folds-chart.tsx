import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Cell } from 'recharts'
import {
  ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
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

// The --chart-N vars are complete oklch() colours (Tailwind 4 / shadcn v4);
// reference them directly — wrapping in hsl() produces invalid CSS (black).
const metricColors: Record<string, string> = {
  mae: 'var(--chart-1)',
  smape: 'var(--chart-2)',
  wape: 'var(--chart-3)',
  bias: 'var(--chart-4)',
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
        {/* Height is passed via inline style — a `h-[${height}px]` class is a
            dynamic string Tailwind cannot statically discover, so the JIT
            compiler drops it at build time. */}
        <ChartContainer config={chartConfig} className="w-full" style={{ height: `${height}px` }}>
          <BarChart data={formattedData} accessibilityLayer>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="foldLabel" tickLine={false} axisLine={false} />
            <YAxis tickLine={false} axisLine={false} />
            <ChartTooltip content={<ChartTooltipContent />} />
            <ChartLegend content={<ChartLegendContent />} />
            <Bar
              dataKey={metricKey}
              name={metricLabels[metricKey]}
              fill={metricColors[metricKey]}
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
