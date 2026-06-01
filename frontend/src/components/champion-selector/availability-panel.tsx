import { AlertTriangle, DatabaseZap } from 'lucide-react'
import { EmptyState } from '@/components/common/error-display'
import { LoadingState } from '@/components/common/loading-state'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatNumber, formatPercent } from '@/lib/api'
import type { AvailabilityStatus, PairAvailability } from '@/types/api'

interface AvailabilityPanelProps {
  availability?: PairAvailability
  isLoading: boolean
  isError: boolean
}

const STATUS_VARIANT: Record<
  AvailabilityStatus,
  'default' | 'secondary' | 'destructive'
> = {
  ready: 'default',
  limited: 'secondary',
  unusable: 'destructive',
}

const STATUS_LABEL: Record<AvailabilityStatus, string> = {
  ready: 'Ready',
  limited: 'Limited',
  unusable: 'Unusable',
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-muted/30 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-0.5 text-lg font-semibold tabular-nums">{value}</p>
    </div>
  )
}

/**
 * Renders the (store, product) data-availability triage for the Champion
 * Selector. Slice A surfaces the backend assessment only — no run, no charts.
 */
export function AvailabilityPanel({
  availability,
  isLoading,
  isError,
}: AvailabilityPanelProps) {
  if (isLoading) {
    return <LoadingState message="Assessing data availability…" />
  }

  if (isError) {
    return (
      <EmptyState
        title="Could not assess availability"
        description="The availability check failed for this pair. Try a different store/product or check the backend."
        icon={<AlertTriangle className="h-12 w-12" />}
      />
    )
  }

  if (!availability) {
    return (
      <EmptyState
        title="Pick a store and product"
        description="Choose a valid store, product and horizon to see whether the pair has enough history to model."
        icon={<DatabaseZap className="h-12 w-12" />}
      />
    )
  }

  // Not-enough-data state: an unusable pair or one with zero observed history.
  if (availability.status === 'unusable' || availability.observed_days === 0) {
    return (
      <EmptyState
        title="Not enough data to model this pair"
        description="This store/product pair has too little observed sales history for a reliable comparison. Pick a different pair or a longer window."
        icon={<DatabaseZap className="h-12 w-12" />}
      />
    )
  }

  const split = availability.recommended_split_config

  return (
    <Card data-testid="availability-panel">
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-lg">Data availability</CardTitle>
          <Badge
            variant={STATUS_VARIANT[availability.status]}
            data-testid="availability-status-badge"
          >
            {STATUS_LABEL[availability.status]}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <Metric label="Observed days" value={formatNumber(availability.observed_days)} />
          <Metric
            label="Coverage"
            value={formatPercent(availability.coverage_ratio * 100)}
          />
          <Metric label="Zero-sale days" value={formatNumber(availability.zero_sale_days)} />
          <Metric
            label="Promotion days"
            value={
              availability.promotion_days === null
                ? '—'
                : formatNumber(availability.promotion_days)
            }
          />
          <Metric
            label="Avg daily demand"
            value={formatNumber(availability.average_daily_demand, 2)}
          />
        </div>

        <div className="rounded-md border p-3">
          <p className="text-xs font-medium text-muted-foreground">
            Recommended split
          </p>
          <p className="mt-1 text-sm tabular-nums">
            {split.strategy} · {split.n_splits} splits · min train{' '}
            {split.min_train_size}d · gap {split.gap}d · horizon {split.horizon}d
          </p>
        </div>

        {availability.warnings.length > 0 && (
          <ul className="space-y-1">
            {availability.warnings.map((warning, index) => (
              <li
                key={index}
                className="flex items-start gap-2 text-xs text-muted-foreground"
              >
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
                <span>{warning}</span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
