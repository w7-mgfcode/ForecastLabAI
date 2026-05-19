import { CartesianGrid, ComposedChart, Line, XAxis, YAxis } from 'recharts'
import {
  ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from '@/components/ui/chart'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

/** One line in a multi-series chart — a row key plus its display label. */
export interface ChartSeries {
  key: string
  label: string
}

interface MultiSeriesChartProps {
  title: string
  description?: string
  /** Date-keyed rows; each carries `xAxisKey` plus a value per series key. */
  data: Record<string, number | string>[]
  /** The lines to draw — the first is rendered solid, the rest dashed. */
  series: ChartSeries[]
  xAxisKey?: string
  height?: number
  className?: string
}

// Deterministic palette — the shadcn chart CSS vars cycled across the lines.
const PALETTE = [
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-4)',
  'var(--chart-5)',
]

/**
 * Renders M+1 demand lines on one chart — a shared baseline plus one line per
 * scenario — for the What-If Planner's multi-scenario comparison view.
 *
 * Every series key MUST be a valid CSS identifier (the shadcn `ChartContainer`
 * emits a `--color-<key>` var per key); callers key scenario lines by the
 * CSS-safe `scenario_id`, never by a free-text plan name.
 */
export function MultiSeriesChart({
  title,
  description,
  data,
  series,
  xAxisKey = 'date',
  height = 320,
  className,
}: MultiSeriesChartProps) {
  const chartConfig: ChartConfig = {}
  series.forEach((line, index) => {
    chartConfig[line.key] = {
      label: line.label,
      color: PALETTE[index % PALETTE.length],
    }
  })

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>
        {/* Height via inline style — a dynamic `h-[${height}px]` class is not
            statically discoverable by the Tailwind JIT compiler. */}
        <ChartContainer config={chartConfig} className="w-full" style={{ height: `${height}px` }}>
          <ComposedChart data={data} accessibilityLayer>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis
              dataKey={xAxisKey}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value: string) => {
                const date = new Date(value)
                return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
              }}
            />
            <YAxis tickLine={false} axisLine={false} />
            <ChartTooltip content={<ChartTooltipContent />} />
            <ChartLegend content={<ChartLegendContent />} />
            {series.map((line, index) => (
              <Line
                key={line.key}
                type="monotone"
                dataKey={line.key}
                stroke={`var(--color-${line.key})`}
                strokeWidth={2}
                strokeDasharray={index === 0 ? undefined : '5 5'}
                dot={false}
                name={line.label}
                connectNulls
              />
            ))}
          </ComposedChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
