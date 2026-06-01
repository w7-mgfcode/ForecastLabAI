import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { BIAS_EXPLANATION } from '@/components/champion-selector/copy'
import type { ForecastDecision } from '@/types/api'

interface BusinessInterpretationPanelProps {
  /** The deterministic backend `business_summary` (read-only). */
  businessSummary: Record<string, unknown> | null
  /** The decision heuristic (carries bias-risk text + expected demand). */
  decision: ForecastDecision | null
}

function str(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

/**
 * Slice C — business interpretation. Renders the SAME `business_summary` the
 * backend computed (read-only — Slice B's winner card owns the headline) and
 * ADDS the decision-layer fields (expected demand + bias risk + caveats).
 */
export function BusinessInterpretationPanel({
  businessSummary,
  decision,
}: BusinessInterpretationPanelProps) {
  const headline = str(businessSummary?.['headline'])
  const winner = businessSummary?.['winner'] as Record<string, unknown> | null | undefined
  const winnerSummary = str(winner?.['summary'])
  const comparison = businessSummary?.['comparison'] as Record<string, unknown> | null | undefined
  const leadText = str(comparison?.['lead_text'])
  const dataNotes = Array.isArray(businessSummary?.['data_notes'])
    ? (businessSummary?.['data_notes'] as unknown[]).filter((x): x is string => typeof x === 'string')
    : []

  return (
    <Card data-testid="business-interpretation-panel">
      <CardHeader>
        <CardTitle>Business interpretation</CardTitle>
        {headline && <CardDescription>{headline}</CardDescription>}
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {winnerSummary && (
          <p>
            <span className="font-medium">Why it won: </span>
            {winnerSummary}
            {leadText ? ` — ${leadText}.` : '.'}
          </p>
        )}

        {decision && (
          <div className="space-y-2">
            <p data-testid="business-expected-demand">
              <span className="font-medium">Expected demand over lead time: </span>
              {decision.expected_demand_over_lead_time.toFixed(1)} units (
              {decision.lead_time_days} days).
            </p>
            <p className="text-muted-foreground" data-testid="business-bias-risk">
              {decision.bias_risk_text}
            </p>
          </div>
        )}

        {!decision && (
          <p className="text-xs text-muted-foreground">{BIAS_EXPLANATION}</p>
        )}

        {dataNotes.length > 0 && (
          <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">
            {dataNotes.map((note, i) => (
              <li key={i}>{note}</li>
            ))}
          </ul>
        )}

        {decision?.caveats?.length ? (
          <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">
            {decision.caveats.map((caveat, i) => (
              <li key={i}>{caveat}</li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  )
}
