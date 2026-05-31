import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { sortBuckets } from '@/lib/horizon-bucket-utils'

/**
 * PRP-37 Slice C — per-horizon-bucket metric table. Reads
 * ModelBacktestResult.bucketed_aggregated_metrics (PRP-36 dict-of-dict
 * shape: bucket_id → metric_name → value). Empty bucket dict, undefined
 * bucketed payload, or no rows for the chosen metric all render the
 * "no horizon-bucket metrics available" empty state.
 */

export type HorizonBucketMetric =
  | 'mae'
  | 'smape'
  | 'wape'
  | 'bias'
  | 'rmse'

interface HorizonBucketTableProps {
  bucketed:
    | Record<string, Record<string, number>>
    | null
    | undefined
  metric: HorizonBucketMetric
  metricLabel?: string
}

export function HorizonBucketTable({
  bucketed,
  metric,
  metricLabel,
}: HorizonBucketTableProps) {
  if (!bucketed || Object.keys(bucketed).length === 0) {
    return (
      <p
        className="text-muted-foreground text-sm"
        data-testid="horizon-bucket-table-empty"
      >
        No horizon-bucket metrics available.
      </p>
    )
  }
  const sortedIds = sortBuckets(Object.keys(bucketed))
  return (
    <Table data-testid="horizon-bucket-table">
      <TableHeader>
        <TableRow>
          <TableHead>Bucket</TableHead>
          <TableHead className="text-right">
            {metricLabel ?? metric.toUpperCase()}
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sortedIds.map((id) => {
          const value = bucketed[id]?.[metric]
          return (
            <TableRow key={id} data-testid={`horizon-bucket-row-${id}`}>
              <TableCell className="font-mono text-xs">{id}</TableCell>
              <TableCell className="text-right tabular-nums">
                {typeof value === 'number' ? formatBucketValue(value) : '—'}
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )

  function formatBucketValue(v: number): string {
    if (!Number.isFinite(v)) return '—'
    return v.toFixed(2)
  }
}
