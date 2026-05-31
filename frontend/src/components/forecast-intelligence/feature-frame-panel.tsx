import { Layers, ShieldAlert } from 'lucide-react'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { Badge } from '@/components/ui/badge'
import { StatusBadge } from '@/components/common/status-badge'
import { LoadingState } from '@/components/common/loading-state'
import {
  labelForGroup,
  labelForSafetyClass,
  safetyClassChipVariant,
} from '@/lib/feature-frame-utils'
import type {
  FeatureFrameVersion,
  FeatureGroup,
  FeatureSafetyClass,
} from '@/types/api'

/**
 * PRP-37 Slice C — read-only "Feature frame" panel for the run detail page.
 * Renders V1/V2 chip, per-group collapsible column list, and per-column
 * safety chips. Pre-PRP-35 runs (no fields set) render the empty state.
 */

interface FeatureFramePanelProps {
  feature_frame_version?: FeatureFrameVersion | null
  feature_groups?: Partial<Record<FeatureGroup, string[]>> | null
  feature_safety_classes?: Record<string, FeatureSafetyClass> | null
  isLoading?: boolean
}

export function FeatureFramePanel({
  feature_frame_version,
  feature_groups,
  feature_safety_classes,
  isLoading,
}: FeatureFramePanelProps) {
  if (isLoading) {
    return (
      <Card data-testid="feature-frame-panel">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Layers className="h-5 w-5" aria-hidden />
            Feature frame
          </CardTitle>
        </CardHeader>
        <CardContent>
          <LoadingState message="Loading feature frame…" />
        </CardContent>
      </Card>
    )
  }

  const hasVersion =
    feature_frame_version !== undefined && feature_frame_version !== null
  const hasGroups =
    feature_groups != null && Object.keys(feature_groups).length > 0
  if (!hasVersion && !hasGroups) {
    return (
      <Card data-testid="feature-frame-panel">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Layers className="h-5 w-5" aria-hidden />
            Feature frame
          </CardTitle>
          <CardDescription>
            Feature frame information not available (pre-PRP-35 run).
          </CardDescription>
        </CardHeader>
      </Card>
    )
  }

  const version: FeatureFrameVersion =
    feature_frame_version === 2 ? 2 : 1
  return (
    <Card data-testid="feature-frame-panel">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Layers className="h-5 w-5" aria-hidden />
          Feature frame
          <Badge
            variant={version === 2 ? 'default' : 'secondary'}
            data-testid="feature-frame-version-chip"
          >
            {version === 2 ? 'V2 — feature-aware' : 'V1 — target-only'}
          </Badge>
        </CardTitle>
        <CardDescription>
          The feature contract this run consumed at training time.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {version === 1 && !hasGroups && (
          <p className="text-muted-foreground text-sm">
            V1 runs use a target-only feature frame (lags + same-DOW mean);
            no per-pack metadata to render.
          </p>
        )}
        {hasGroups && feature_groups && (
          <div className="space-y-2">
            {Object.entries(feature_groups).map(([group, cols]) => {
              const columns = cols ?? []
              return (
                <Collapsible key={group} defaultOpen={false}>
                  <CollapsibleTrigger
                    className="bg-muted/40 hover:bg-muted flex w-full items-center justify-between rounded-md border px-3 py-2 text-sm"
                    data-testid={`feature-frame-group-${group}`}
                  >
                    <span className="flex items-center gap-2 font-medium">
                      {labelForGroup(group as FeatureGroup)}
                      <Badge variant="outline" className="font-mono text-xs">
                        {columns.length}
                      </Badge>
                    </span>
                    <span className="text-muted-foreground text-xs">
                      expand
                    </span>
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <ul className="bg-background space-y-1 rounded-md border border-t-0 px-3 py-2">
                      {columns.length === 0 && (
                        <li className="text-muted-foreground text-xs">
                          (no columns)
                        </li>
                      )}
                      {columns.map((col) => {
                        const safety = feature_safety_classes?.[col]
                        return (
                          <li
                            key={col}
                            className="flex items-center justify-between text-xs"
                            data-testid={`feature-frame-column-${col}`}
                          >
                            <span className="font-mono">{col}</span>
                            {safety && (
                              <StatusBadge
                                variant={safetyClassChipVariant(safety)}
                              >
                                {labelForSafetyClass(safety)}
                              </StatusBadge>
                            )}
                          </li>
                        )
                      })}
                    </ul>
                  </CollapsibleContent>
                </Collapsible>
              )
            })}
          </div>
        )}
        {feature_safety_classes &&
          Object.values(feature_safety_classes).some(
            (s) => s === 'unsafe_unless_supplied',
          ) && (
            <p
              className="text-warning flex items-center gap-1.5 text-xs"
              data-testid="feature-frame-safety-warning"
            >
              <ShieldAlert className="h-3.5 w-3.5" aria-hidden />
              At least one column requires supplied data — promote this run
              only if the production pipeline supplies it.
            </p>
          )}
      </CardContent>
    </Card>
  )
}
