import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { MultiSeriesChart } from '@/components/charts/multi-series-chart'
import { BIAS_EXPLANATION } from '@/components/champion-selector/copy'
import type { ModelSelectionChartData } from '@/types/api'

interface ComparisonChartsProps {
  chartData: ModelSelectionChartData
  winnerModelType?: string
}

/** One labelled horizontal bar (CSS — deterministic, no chart lib needed). */
function MetricBars({
  title,
  byModel,
  winnerModelType,
  signed = false,
}: {
  title: string
  byModel: Record<string, number>
  winnerModelType?: string
  signed?: boolean
}) {
  const entries = Object.entries(byModel)
  const max = Math.max(1, ...entries.map(([, v]) => Math.abs(v)))
  return (
    <div className="space-y-2" data-testid={`metric-bars-${title.toLowerCase().replace(/\s+/g, '-')}`}>
      <p className="text-xs font-medium text-muted-foreground">{title}</p>
      {entries.map(([model, value]) => (
        <div key={model} className="flex items-center gap-2 text-xs">
          <span className="w-28 shrink-0 truncate" title={model}>
            {model === winnerModelType ? `★ ${model}` : model}
          </span>
          <div className="h-3 flex-1 rounded bg-muted">
            <div
              className={signed && value < 0 ? 'h-3 rounded bg-amber-500' : 'h-3 rounded bg-primary'}
              style={{ width: `${(Math.abs(value) / max) * 100}%` }}
            />
          </div>
          <span className="w-12 shrink-0 text-right tabular-nums">{value.toFixed(2)}</span>
        </div>
      ))}
    </div>
  )
}

/**
 * Comparison charts (Slice B): WAPE-by-model + bias-by-model bars, and the
 * winner's actual-vs-predicted overlay. Reads the backend `chart_data` payload.
 */
export function ComparisonCharts({ chartData, winnerModelType }: ComparisonChartsProps) {
  // Build actual-vs-predicted rows for the winner from the fold chart points.
  const avpRows: Record<string, number | string>[] = []
  for (const fold of chartData.winner_actual_vs_predicted as Array<{
    dates?: string[]
    actuals?: number[]
    predictions?: number[]
  }>) {
    const dates = fold.dates ?? []
    const actuals = fold.actuals ?? []
    const predictions = fold.predictions ?? []
    for (let i = 0; i < dates.length; i++) {
      avpRows.push({
        date: dates[i] ?? String(i),
        actual: actuals[i] ?? 0,
        predicted: predictions[i] ?? 0,
      })
    }
  }

  return (
    <Card data-testid="comparison-charts">
      <CardHeader>
        <CardTitle>Comparison</CardTitle>
        <CardDescription>{BIAS_EXPLANATION}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="grid gap-6 md:grid-cols-2">
          <MetricBars
            title="WAPE by model"
            byModel={chartData.wape_by_model}
            winnerModelType={winnerModelType}
          />
          <MetricBars
            title="Bias by model"
            byModel={chartData.bias_by_model}
            winnerModelType={winnerModelType}
            signed
          />
        </div>
        {avpRows.length > 0 && (
          <MultiSeriesChart
            title="Winner — actual vs predicted"
            data={avpRows}
            series={[
              { key: 'actual', label: 'Actual' },
              { key: 'predicted', label: 'Predicted' },
            ]}
            xAxisKey="date"
            height={260}
          />
        )}
      </CardContent>
    </Card>
  )
}
