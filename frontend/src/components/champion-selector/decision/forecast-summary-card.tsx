import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { ModelSelectionForecastSummary } from '@/types/api'

interface ForecastSummaryCardProps {
  forecast: ModelSelectionForecastSummary
}

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-md border bg-muted/30 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-lg font-semibold tabular-nums">{value}</p>
      {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
    </div>
  )
}

function num(value: number | null | undefined): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(1) : '—'
}

/** Slice C — total / average / peak / low / horizon KPI tiles (null-safe). */
export function ForecastSummaryCard({ forecast }: ForecastSummaryCardProps) {
  return (
    <Card data-testid="forecast-summary-card">
      <CardHeader>
        <CardTitle>Forecast summary</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <Tile label="Total demand" value={num(forecast.total_demand)} />
          <Tile label="Average / day" value={num(forecast.average_demand)} />
          <Tile
            label="Peak day"
            value={num(forecast.peak_demand)}
            sub={forecast.peak_date ?? undefined}
          />
          <Tile
            label="Low day"
            value={num(forecast.low_demand)}
            sub={forecast.low_date ?? undefined}
          />
          <Tile label="Horizon" value={`${forecast.horizon}d`} />
        </div>
      </CardContent>
    </Card>
  )
}
