import { Trophy } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { StatusBadge } from '@/components/common/status-badge'
import { BIAS_EXPLANATION } from '@/components/champion-selector/copy'
import type { ConfidenceLevel, WinnerSummary } from '@/types/api'

interface WinnerCardProps {
  winner: WinnerSummary | null
  confidence: ConfidenceLevel | null
  reasons: string[]
  /** The deterministic backend `business_summary` (read-only; Slice C extends). */
  businessSummary?: Record<string, unknown> | null
}

const CONFIDENCE_VARIANT: Record<ConfidenceLevel, 'success' | 'info' | 'warning'> = {
  high: 'success',
  medium: 'info',
  low: 'warning',
}

function Metric({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="rounded-md border bg-muted/30 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-lg font-semibold tabular-nums">
        {typeof value === 'number' && Number.isFinite(value) ? value.toFixed(2) : '—'}
      </p>
    </div>
  )
}

/**
 * Winner summary card (Slice B). Null-safe — renders a "no winner" state for a
 * failed/cancelled run. Renders the deterministic `business_summary` headline
 * READ-ONLY (Slice C adds the decision-layer interpretation on top).
 */
export function WinnerCard({ winner, confidence, reasons, businessSummary }: WinnerCardProps) {
  if (winner === null) {
    return (
      <Card data-testid="winner-card">
        <CardHeader>
          <CardTitle>No champion selected</CardTitle>
          <CardDescription>
            No candidate produced a valid backtest. Review the failed candidates
            below or adjust the selection.
          </CardDescription>
        </CardHeader>
      </Card>
    )
  }

  const headline =
    typeof businessSummary?.['headline'] === 'string'
      ? (businessSummary['headline'] as string)
      : null

  return (
    <Card data-testid="winner-card">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2">
            <Trophy className="h-5 w-5" />
            {winner.model_type}
          </CardTitle>
          {confidence && (
            <StatusBadge
              variant={CONFIDENCE_VARIANT[confidence]}
              data-testid="winner-confidence-badge"
            >
              {confidence} confidence
            </StatusBadge>
          )}
        </div>
        {headline && <CardDescription>{headline}</CardDescription>}
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Metric label="WAPE" value={winner.metrics['wape']} />
          <Metric label="sMAPE" value={winner.metrics['smape']} />
          <Metric label="MAE" value={winner.metrics['mae']} />
          <Metric label="Bias" value={winner.metrics['bias']} />
        </div>
        {reasons.length > 0 && (
          <div className="space-y-1">
            {reasons.map((reason, i) => (
              <div key={i} className="flex items-start gap-2">
                <Badge variant="secondary" className="mt-0.5 shrink-0">
                  why
                </Badge>
                <span className="text-sm text-muted-foreground">{reason}</span>
              </div>
            ))}
          </div>
        )}
        <p className="text-xs text-muted-foreground">{BIAS_EXPLANATION}</p>
      </CardContent>
    </Card>
  )
}
