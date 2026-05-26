import { labelForBucket, sortBuckets } from '@/lib/horizon-bucket-utils'

export type BucketMetric = 'wape' | 'mae' | 'rmse' | 'bias' | 'smape'

interface HorizonBucketsMiniProps {
  bucketed: Record<string, Record<string, number>>
  metric?: BucketMetric
}

/**
 * PRP-38 — small 4-row table for per-horizon-bucket metrics on the backtest
 * step card. Reuses `sortBuckets` + `labelForBucket` from
 * `lib/horizon-bucket-utils.ts` (PRP-37 helper) so the bucket order matches
 * the rest of the dashboard.
 */
export function HorizonBucketsMini({ bucketed, metric = 'wape' }: HorizonBucketsMiniProps) {
  const ids = sortBuckets(Object.keys(bucketed))
  if (ids.length === 0) {
    return (
      <p className="mt-3 text-xs text-muted-foreground">
        No horizon-bucket metrics available
      </p>
    )
  }
  return (
    <div className="mt-3 space-y-1">
      <p className="text-xs font-medium text-muted-foreground">
        Per-horizon bucket {metric.toUpperCase()}
      </p>
      <div className="overflow-hidden rounded-md border">
        <table className="w-full text-xs">
          <tbody>
            {ids.map((id) => {
              const metrics = bucketed[id] ?? {}
              const value = metrics[metric]
              return (
                <tr key={id} className="border-b last:border-b-0">
                  <td className="px-2 py-1 font-mono text-muted-foreground">
                    {labelForBucket(id)}
                  </td>
                  <td className="px-2 py-1 text-right font-mono">
                    {typeof value === 'number' && Number.isFinite(value)
                      ? value.toFixed(4)
                      : 'n/a'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
