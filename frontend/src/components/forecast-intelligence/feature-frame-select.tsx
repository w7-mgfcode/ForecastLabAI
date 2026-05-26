import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { Info } from 'lucide-react'
import type { FeatureFrameVersion } from '@/types/api'

/**
 * PRP-37 Slice C — V1/V2 feature-frame selector. V2 is disabled when the
 * server has not shipped Forecast Intelligence A (PRP-35); the tooltip
 * carries the human-readable reason so the disabled state is never silent.
 */

interface FeatureFrameSelectProps {
  value: FeatureFrameVersion
  onChange: (value: FeatureFrameVersion) => void
  isV2Available: boolean
  v2DisabledReason?: string
  className?: string
}

const DEFAULT_V2_REASON =
  'V2 unavailable — server has not shipped Forecast Intelligence A.'

export function FeatureFrameSelect({
  value,
  onChange,
  isV2Available,
  v2DisabledReason,
  className,
}: FeatureFrameSelectProps) {
  return (
    <div className={`flex items-center gap-2 ${className ?? ''}`}>
      <Select
        value={String(value)}
        onValueChange={(next) =>
          onChange(Number(next) === 2 ? 2 : 1)
        }
      >
        <SelectTrigger
          className="w-[220px]"
          data-testid="feature-frame-select-trigger"
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="1">V1 — target-only</SelectItem>
          <SelectItem value="2" disabled={!isV2Available}>
            V2 — feature-aware
          </SelectItem>
        </SelectContent>
      </Select>
      {!isV2Available && (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger
              asChild
              data-testid="feature-frame-v2-disabled-tooltip"
            >
              <span className="text-muted-foreground inline-flex h-4 w-4 cursor-help items-center">
                <Info className="h-4 w-4" aria-label="V2 disabled" />
              </span>
            </TooltipTrigger>
            <TooltipContent>
              {v2DisabledReason ?? DEFAULT_V2_REASON}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      )}
    </div>
  )
}
