import { LineChart, Line, XAxis, YAxis, CartesianGrid, Legend } from 'recharts'
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
  [key: string]: string | number | undefined
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
  height = 300,
  className,
}: TimeSeriesChartProps) {
  const chartConfig: ChartConfig = {
    [actualKey]: {
      label: 'Actual',
      color: 'hsl(var(--chart-1))',
    },
    [predictedKey]: {
      label: 'Predicted',
      color: 'hsl(var(--chart-2))',
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
          <LineChart data={data} accessibilityLayer>
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
            {showActual && (
              <Line
                type="monotone"
                dataKey={actualKey}
                stroke="var(--color-actual)"
                strokeWidth={2}
                dot={false}
                name="Actual"
              />
            )}
            {showPredicted && (
              <Line
                type="monotone"
                dataKey={predictedKey}
                stroke="var(--color-predicted)"
                strokeWidth={2}
                strokeDasharray="5 5"
                dot={false}
                name="Predicted"
              />
            )}
          </LineChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
