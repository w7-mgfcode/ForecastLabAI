import { TimeSeriesChart } from '@/components/charts/time-series-chart'
import type { ModelSelectionForecastSummary } from '@/types/api'

interface ForecastChartProps {
  forecast: ModelSelectionForecastSummary
}

interface ChartRow {
  date: string
  forecast: number
  lower?: number
  upper?: number
}

/** Slice C — the horizon forecast curve (optional interval band). */
export function ForecastChart({ forecast }: ForecastChartProps) {
  const rows: ChartRow[] = forecast.points.map((point) => {
    const lower = point['lower_bound']
    const upper = point['upper_bound']
    return {
      date: String(point['date'] ?? ''),
      forecast: Number(point['forecast'] ?? 0),
      lower: typeof lower === 'number' ? lower : undefined,
      upper: typeof upper === 'number' ? upper : undefined,
    }
  })
  const hasInterval = rows.some((row) => row.lower !== undefined && row.upper !== undefined)

  return (
    <div data-testid="forecast-chart">
      <TimeSeriesChart
        title="Forecast"
        description="Predicted demand over the forecast horizon."
        data={rows}
        predictedKey="forecast"
        showActual={false}
        lowerKey="lower"
        upperKey="upper"
        showInterval={hasInterval}
      />
    </div>
  )
}
