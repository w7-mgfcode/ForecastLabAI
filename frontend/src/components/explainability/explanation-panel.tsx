import type { ReactNode } from 'react'
import { AlertTriangle, Info, Lightbulb, Minus, TrendingDown, TrendingUp } from 'lucide-react'
import { ApiError, formatNumber, getErrorMessage } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { LoadingState } from '@/components/common/loading-state'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type {
  ConfidenceLevel,
  DriverContribution,
  ForecastExplanation,
  ReasonCode,
} from '@/types/api'

interface ExplanationPanelProps {
  explanation?: ForecastExplanation
  isLoading?: boolean
  error?: unknown
}

const CONFIDENCE_VARIANT: Record<ConfidenceLevel, 'default' | 'secondary' | 'outline'> = {
  high: 'default',
  medium: 'secondary',
  low: 'outline',
}

function DirectionLabel({ direction }: { direction: DriverContribution['direction'] }) {
  if (direction === 'positive') {
    return (
      <span className="flex items-center gap-1 text-success">
        <TrendingUp className="h-3.5 w-3.5" />
        Positive
      </span>
    )
  }
  if (direction === 'negative') {
    return (
      <span className="flex items-center gap-1 text-destructive">
        <TrendingDown className="h-3.5 w-3.5" />
        Negative
      </span>
    )
  }
  return (
    <span className="flex items-center gap-1 text-muted-foreground">
      <Minus className="h-3.5 w-3.5" />
      Neutral
    </span>
  )
}

function ReasonCodeRow({ reason }: { reason: ReasonCode }) {
  const isWarn = reason.severity === 'warn'
  return (
    <li className="flex items-start gap-2 text-sm">
      {isWarn ? (
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
      ) : (
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
      )}
      <span>
        <span className="font-medium">{reason.code.replace(/_/g, ' ')}</span>
        {' — '}
        {reason.detail}
      </span>
    </li>
  )
}

/** Card shell shared by every panel state so the layout never jumps. */
function PanelShell({ children }: { children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Lightbulb className="h-5 w-5" />
          Forecast Explanation
        </CardTitle>
        <CardDescription>
          Rule-based driver attribution for the h=1 baseline forecast.
        </CardDescription>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

export function ExplanationPanel({ explanation, isLoading, error }: ExplanationPanelProps) {
  if (isLoading) {
    return (
      <PanelShell>
        <LoadingState message="Generating explanation..." />
      </PanelShell>
    )
  }

  if (error) {
    // A 400 here means the run/job is not a baseline model — an expected,
    // non-error outcome, so it is shown in a neutral (not destructive) tone.
    const isExpected = error instanceof ApiError && error.status === 400
    return (
      <PanelShell>
        <div
          className={
            isExpected
              ? 'flex items-start gap-2 rounded-md border bg-muted/40 p-3 text-sm text-muted-foreground'
              : 'flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive'
          }
        >
          {isExpected ? (
            <Info className="mt-0.5 h-4 w-4 shrink-0" />
          ) : (
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          )}
          <span>{getErrorMessage(error)}</span>
        </div>
      </PanelShell>
    )
  }

  if (!explanation) {
    return (
      <PanelShell>
        <p className="text-sm text-muted-foreground">No explanation available.</p>
      </PanelShell>
    )
  }

  return (
    <PanelShell>
      <div className="space-y-5">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <div>
            <p className="text-xs text-muted-foreground">h=1 forecast</p>
            <p className="text-2xl font-bold">{formatNumber(explanation.forecast_value, 1)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Confidence</p>
            <Badge variant={CONFIDENCE_VARIANT[explanation.confidence]}>
              {explanation.confidence}
            </Badge>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Model</p>
            <p className="font-medium">{explanation.model_type}</p>
          </div>
        </div>

        <p className="text-sm text-muted-foreground">{explanation.agent_summary}</p>

        <div className="space-y-2">
          <h4 className="text-sm font-semibold">Drivers</h4>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Driver</TableHead>
                <TableHead className="text-right">Value</TableHead>
                <TableHead className="text-right">Contribution</TableHead>
                <TableHead>Direction</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {explanation.drivers.map((driver) => (
                <TableRow key={driver.name}>
                  <TableCell>
                    <span className="font-medium">{driver.name.replace(/_/g, ' ')}</span>
                    <span className="block text-xs text-muted-foreground">
                      {driver.description}
                    </span>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatNumber(driver.feature_value, 1)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatNumber(driver.contribution, 1)}
                  </TableCell>
                  <TableCell>
                    <DirectionLabel direction={driver.direction} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        <div className="space-y-2">
          <h4 className="text-sm font-semibold">Retail signals</h4>
          {explanation.reason_codes.length > 0 ? (
            <ul className="space-y-1.5">
              {explanation.reason_codes.map((reason) => (
                <ReasonCodeRow key={reason.code} reason={reason} />
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">
              No advisory retail signals were detected.
            </p>
          )}
        </div>

        <div className="space-y-1 border-t pt-3">
          {explanation.caveats.map((caveat) => (
            <p key={caveat} className="text-xs text-muted-foreground">
              {caveat}
            </p>
          ))}
        </div>
      </div>
    </PanelShell>
  )
}
