import { Loader2, LineChart, Ban } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { FEATURE_AWARE_BLOCKED_COPY } from './constants'

interface TrainForecastActionsProps {
  /** From the Slice A catalog (`supports_auto_predict = not feature_aware`). */
  supportsAutoPredict: boolean
  /** True once a model bundle has been trained for the selection. */
  trained: boolean
  isPredicting: boolean
  onForecast: () => void
}

/**
 * Slice C — the Forecast action + the capability-limited blocked state.
 *
 * A feature-aware winner cannot auto-predict (LOCKED #5): instead of faking a
 * forecast we surface the limitation and route the user to the What-If Planner.
 */
export function TrainForecastActions({
  supportsAutoPredict,
  trained,
  isPredicting,
  onForecast,
}: TrainForecastActionsProps) {
  if (!supportsAutoPredict) {
    return (
      <div
        className="flex items-start gap-2 rounded-md border border-muted bg-muted/30 p-3 text-sm text-muted-foreground"
        data-testid="forecast-blocked-state"
      >
        <Ban className="mt-0.5 h-4 w-4 shrink-0" />
        <span>{FEATURE_AWARE_BLOCKED_COPY}</span>
      </div>
    )
  }

  return (
    <Button
      type="button"
      variant="secondary"
      onClick={onForecast}
      disabled={!trained || isPredicting}
      data-testid="forecast-button"
    >
      {isPredicting ? (
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
      ) : (
        <LineChart className="mr-2 h-4 w-4" />
      )}
      {trained ? 'Generate forecast' : 'Train a model first'}
    </Button>
  )
}
