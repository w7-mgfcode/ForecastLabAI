import { BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts'
import {
  ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from '@/components/ui/chart'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

interface RevenueBarDatum {
  label: string
  revenue: number
}

interface RevenueBarChartProps {
  title: string
  description?: string
  data: RevenueBarDatum[]
  height?: number
  className?: string
}

// The --chart-N vars are complete oklch() colours (Tailwind 4 / shadcn v4);
// reference them directly — wrapping in hsl() produces invalid CSS (black).
const chartConfig: ChartConfig = {
  revenue: { label: 'Revenue', color: 'var(--chart-1)' },
}

/** Revenue-by-dimension bar chart. Feed Number()-coerced revenue values. */
export function RevenueBarChart({
  title,
  description,
  data,
  height = 300,
  className,
}: RevenueBarChartProps) {
  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>
        <ChartContainer config={chartConfig} className={`h-[${height}px] w-full`}>
          <BarChart data={data} accessibilityLayer>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="label" tickLine={false} axisLine={false} />
            <YAxis tickLine={false} axisLine={false} />
            <ChartTooltip content={<ChartTooltipContent />} />
            <Bar dataKey="revenue" name="Revenue" fill="var(--chart-1)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
