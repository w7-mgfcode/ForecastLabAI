import { Area, CartesianGrid, ComposedChart, Legend, Line, XAxis, YAxis } from 'recharts'
import {
  ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from '@/components/ui/chart'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

interface TimeSeriesDataPoint {
  date: string
  actual?: number
  predicted?: number
  // `null` is allowed so a forecast point's optional lower/upper bounds (which
  // arrive as `null` for models that emit no interval) can be passed through.
  [key: string]: string | number | null | undefined
}

interface TimeSeriesChartProps {
  title: string
  description?: string
  data: TimeSeriesDataPoint[]
  actualKey?: string
  predictedKey?: string
  xAxisKey?: string
  showActual?: boolean
  showPredicted?: boolean
  /** Row key for the lower bound of the optional prediction-interval band. */
  lowerKey?: string
  /** Row key for the upper bound of the optional prediction-interval band. */
  upperKey?: string
  /** Render a shaded band between lowerKey/upperKey. Default false (opt-in). */
  showInterval?: boolean
  height?: number
  className?: string
}

export function TimeSeriesChart({
  title,
  description,
  data,
  actualKey = 'actual',
  predictedKey = 'predicted',
  xAxisKey = 'date',
  showActual = true,
  showPredicted = true,
  lowerKey,
  upperKey,
  showInterval = false,
  height = 300,
  className,
}: TimeSeriesChartProps) {
  // The --chart-N vars are complete oklch() colours (Tailwind 4 / shadcn v4);
  // reference them directly — wrapping in hsl() produces invalid CSS (black).
  const chartConfig: ChartConfig = {
    [actualKey]: {
      label: 'Actual',
      color: 'var(--chart-1)',
    },
    [predictedKey]: {
      label: 'Predicted',
      color: 'var(--chart-2)',
    },
  }

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>
        <ChartContainer config={chartConfig} className={`h-[${height}px] w-full`}>
          <ComposedChart data={data} accessibilityLayer>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis
              dataKey={xAxisKey}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value: string) => {
                // Format date for display
                const date = new Date(value)
                return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
              }}
            />
            <YAxis tickLine={false} axisLine={false} />
            <ChartTooltip content={<ChartTooltipContent />} />
            <Legend />
            {/* Prediction-interval band — drawn first so the forecast line sits
                on top. A function dataKey returns the [lower, upper] tuple
                recharts renders as a range area. */}
            {showInterval && lowerKey && upperKey && (
              <Area
                type="monotone"
                dataKey={(entry: TimeSeriesDataPoint) => {
                  const lower = entry[lowerKey]
                  const upper = entry[upperKey]
                  return typeof lower === 'number' && typeof upper === 'number'
                    ? [lower, upper]
                    : null
                }}
                name="Prediction interval"
                fill="var(--chart-2)"
                fillOpacity={0.15}
                stroke="none"
                isAnimationActive={false}
              />
            )}
            {showActual && (
              <Line
                type="monotone"
                dataKey={actualKey}
                stroke={`var(--color-${actualKey})`}
                strokeWidth={2}
                dot={false}
                name="Actual"
              />
            )}
            {showPredicted && (
              <Line
                type="monotone"
                dataKey={predictedKey}
                stroke={`var(--color-${predictedKey})`}
                strokeWidth={2}
                strokeDasharray="5 5"
                dot={false}
                name="Predicted"
              />
            )}
          </ComposedChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
