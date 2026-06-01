import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { ModelSelectionForecastSummary } from '@/types/api'

interface DailyForecastTableProps {
  forecast: ModelSelectionForecastSummary
}

function cell(value: unknown): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(2) : '—'
}

/** Slice C — the per-day forecast table (date, forecast, lower, upper). */
export function DailyForecastTable({ forecast }: DailyForecastTableProps) {
  return (
    <Card data-testid="daily-forecast-table">
      <CardHeader>
        <CardTitle>Daily forecast</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Date</TableHead>
              <TableHead className="text-right">Forecast</TableHead>
              <TableHead className="text-right">Lower</TableHead>
              <TableHead className="text-right">Upper</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {forecast.points.map((point, index) => (
              <TableRow key={String(point['date'] ?? index)}>
                <TableCell>{String(point['date'] ?? '—')}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {cell(point['forecast'])}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {cell(point['lower_bound'])}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {cell(point['upper_bound'])}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}
