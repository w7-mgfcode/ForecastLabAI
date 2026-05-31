import { Badge } from '@/components/ui/badge'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import type { ModelRun } from '@/types/api'
import { computeCompatibility } from './champion-compatibility-utils'

/**
 * PRP-37 Slice C — comparable-run rule visualization for /explorer/run-compare.
 * Two runs are comparable iff they share grain (store + product), their
 * data windows overlap, AND their feature_frame_version matches (legacy
 * runs default to V1). Computation logic lives in
 * `champion-compatibility-utils.ts` so it can be reused without importing
 * the React surface.
 */

interface ChampionCompatibilityBadgeProps {
  runA: ModelRun
  runB: ModelRun
  className?: string
}

export function ChampionCompatibilityBadge({
  runA,
  runB,
  className,
}: ChampionCompatibilityBadgeProps) {
  const result = computeCompatibility(runA, runB)
  const label = result.ok ? 'Comparable' : 'Not comparable'
  const tooltip = result.ok
    ? 'Same grain, overlapping data windows, same feature frame version.'
    : (result.reason ?? 'Runs do not satisfy the comparable-run rule.')
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge
            variant={result.ok ? 'default' : 'destructive'}
            className={className}
            data-testid="champion-compatibility-badge"
            data-comparable={result.ok ? 'yes' : 'no'}
          >
            {label}
          </Badge>
        </TooltipTrigger>
        <TooltipContent>{tooltip}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
