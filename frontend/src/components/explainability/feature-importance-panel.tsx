import type { ReactNode } from 'react'
import {
  AlertTriangle,
  BarChart3,
  Info,
  Minus,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'
import { ApiError, formatNumber, getErrorMessage } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { LoadingState } from '@/components/common/loading-state'
import { ModelFamilyBadge } from '@/components/common/model-family-badge'
import { cn } from '@/lib/utils'
import type { FeatureImportanceItem, FeatureMetadataResponse } from '@/types/api'

// MLZOO-D / PRP-31 — sibling of ExplanationPanel (PRP-28). One component,
// two display modes: 'tree' (positive-only bars, neutral colour) and
// 'linear_coef' (signed bars with direction colour + icon). The mode is
// selected per item by FeatureImportanceItem.kind so a single panel can
// render any feature-aware family without the consumer page knowing the
// family up front (DECISIONS LOCKED #4).

interface FeatureImportancePanelProps {
  data?: FeatureMetadataResponse
  isLoading?: boolean
  error?: unknown
}

const FAMILY_DESCRIPTION: Record<string, string> = {
  tree: 'Tree-based feature importance (model-derived). Bar length = relative magnitude.',
  additive:
    'Additive Ridge coefficients. Sign indicates direction; bar length = |coefficient|.',
  baseline: 'Feature importance is not available for baseline models.',
}

function PanelShell({
  family,
  importanceType,
  children,
}: {
  family?: FeatureMetadataResponse['model_family']
  importanceType?: string | null
  children: ReactNode
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BarChart3 className="h-5 w-5" />
          Feature Importance
          {family ? <ModelFamilyBadge family={family} /> : null}
        </CardTitle>
        <CardDescription>
          {family ? FAMILY_DESCRIPTION[family] : 'Feature importance for the trained model.'}
          {importanceType ? (
            <span className="ml-2 rounded-md border bg-muted px-1.5 py-0.5 text-[10px] font-mono uppercase tracking-wide text-muted-foreground">
              {importanceType}
            </span>
          ) : null}
        </CardDescription>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

function NeutralMessage({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 rounded-md border bg-muted/40 p-3 text-sm text-muted-foreground">
      <Info className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{message}</span>
    </div>
  )
}

function DestructiveMessage({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{message}</span>
    </div>
  )
}

function ImportanceRow({
  item,
  maxAbs,
}: {
  item: FeatureImportanceItem
  maxAbs: number
}) {
  const widthPercent = maxAbs > 0 ? (Math.abs(item.importance) / maxAbs) * 100 : 0
  const isLinear = item.kind === 'linear_coef'
  const isPositive = item.importance >= 0
  const barColour = isLinear
    ? isPositive
      ? 'bg-success/70'
      : 'bg-destructive/70'
    : 'bg-primary/60'
  const textColour = isLinear
    ? isPositive
      ? 'text-success'
      : 'text-destructive'
    : 'text-foreground'
  const Icon = isLinear ? (isPositive ? TrendingUp : TrendingDown) : Minus
  return (
    <li
      className="grid grid-cols-[8rem_1fr_5rem] items-center gap-2 text-sm"
      data-testid="feature-importance-row"
      data-kind={item.kind}
      data-rank={item.rank}
    >
      <span className="truncate font-mono text-xs text-muted-foreground" title={item.name}>
        {item.name}
      </span>
      <div className="relative h-3 w-full rounded-sm bg-muted">
        <div
          className={cn('absolute inset-y-0 left-0 rounded-sm', barColour)}
          style={{ width: `${widthPercent}%` }}
          aria-hidden
        />
      </div>
      <span className={cn('flex items-center justify-end gap-1 tabular-nums', textColour)}>
        <Icon className="h-3 w-3" aria-hidden />
        {formatNumber(item.importance, 3)}
      </span>
    </li>
  )
}

/** Error-branch helper: pick the right shell + message for an `ApiError`. */
function errorPanel(error: unknown): ReactNode {
  if (error instanceof ApiError) {
    if (error.status === 400) {
      return (
        <PanelShell>
          <NeutralMessage message="Feature importance is available for tree and additive model families only." />
        </PanelShell>
      )
    }
    if (error.status === 422) {
      return (
        <PanelShell>
          <NeutralMessage message="Feature importance is available once training completes and the artifact is saved." />
        </PanelShell>
      )
    }
  }
  return (
    <PanelShell>
      <DestructiveMessage message={getErrorMessage(error)} />
    </PanelShell>
  )
}

export function FeatureImportancePanel({
  data,
  isLoading,
  error,
}: FeatureImportancePanelProps) {
  if (isLoading) {
    return (
      <PanelShell>
        <LoadingState message="Loading feature importance..." />
      </PanelShell>
    )
  }

  if (error) {
    return errorPanel(error)
  }

  if (!data) {
    return null
  }

  if (data.features.length === 0) {
    return (
      <PanelShell family={data.model_family} importanceType={data.importance_type}>
        <NeutralMessage message="No feature importance values are available for this model." />
      </PanelShell>
    )
  }

  const maxAbs = data.features.reduce(
    (acc, item) => Math.max(acc, Math.abs(item.importance)),
    0,
  )

  return (
    <PanelShell family={data.model_family} importanceType={data.importance_type}>
      <ol className="space-y-1.5">
        {data.features.map((item) => (
          <ImportanceRow key={item.name} item={item} maxAbs={maxAbs} />
        ))}
      </ol>
      <p className="mt-4 border-t pt-3 text-xs text-muted-foreground">
        Importance is model-derived. It reflects how much each feature reduced
        the model&apos;s training error — not real-world causation.
      </p>
    </PanelShell>
  )
}
