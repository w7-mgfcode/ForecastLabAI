import { Trophy } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { RANKING_TIE_BREAK } from '@/components/champion-selector/copy'
import type { ModelRankEntry } from '@/types/api'

interface RankingTableProps {
  ranking: ModelRankEntry[]
  onSelectModel: (entry: ModelRankEntry) => void
}

function fmt(value: number | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  return value.toFixed(2)
}

/**
 * Candidate ranking table (Slice B). Winner row highlighted; excluded
 * (failed/cancelled/filtered) rows show their reason and stay visible. Clicking
 * a row opens the model-detail drawer.
 */
export function RankingTable({ ranking, onSelectModel }: RankingTableProps) {
  return (
    <Card data-testid="ranking-table">
      <CardHeader>
        <CardTitle>Ranking</CardTitle>
        <CardDescription>{RANKING_TIE_BREAK}</CardDescription>
      </CardHeader>
      <CardContent>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-muted-foreground">
              <th className="py-1.5">Rank</th>
              <th className="py-1.5">Model</th>
              <th className="py-1.5 text-right">WAPE</th>
              <th className="py-1.5 text-right">sMAPE</th>
              <th className="py-1.5 text-right">MAE</th>
              <th className="py-1.5 text-right">Bias</th>
            </tr>
          </thead>
          <tbody>
            {ranking.map((entry) => (
              <tr
                key={`${entry.model_type}-${entry.rank ?? 'x'}`}
                data-testid={`ranking-row-${entry.model_type}`}
                onClick={() => onSelectModel(entry)}
                className={cn(
                  'cursor-pointer border-t hover:bg-accent/50',
                  entry.rank === 1 && 'bg-primary/5 font-medium',
                  !entry.included && 'text-muted-foreground',
                )}
              >
                <td className="py-1.5">
                  {entry.rank === 1 ? (
                    <span className="inline-flex items-center gap-1">
                      <Trophy className="h-3.5 w-3.5" />1
                    </span>
                  ) : (
                    (entry.rank ?? '—')
                  )}
                </td>
                <td className="py-1.5">
                  {entry.model_type}
                  {!entry.included && (
                    <Badge variant="outline" className="ml-2">
                      {entry.exclusion_reason ?? 'excluded'}
                    </Badge>
                  )}
                </td>
                <td className="py-1.5 text-right tabular-nums">
                  {fmt(entry.metrics?.['wape'])}
                </td>
                <td className="py-1.5 text-right tabular-nums">
                  {fmt(entry.metrics?.['smape'])}
                </td>
                <td className="py-1.5 text-right tabular-nums">
                  {fmt(entry.metrics?.['mae'])}
                </td>
                <td className="py-1.5 text-right tabular-nums">
                  {fmt(entry.metrics?.['bias'])}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  )
}
