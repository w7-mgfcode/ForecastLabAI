import { Loader2, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { ForecastDecision } from '@/types/api'
import { SAFETY_STOCK_HEADER, SERVICE_LEVEL_OPTIONS } from './constants'

interface SafetyStockPanelProps {
  decision: ForecastDecision | null
  leadTimeDays: number
  serviceLevel: number
  isRecomputing: boolean
  onLeadTimeChange: (value: number) => void
  onServiceLevelChange: (value: number) => void
  onRecompute: () => void
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-muted/30 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-lg font-semibold tabular-nums">{value}</p>
    </div>
  )
}

/**
 * Slice C — the CLEARLY-LABELED safety-stock heuristic. Lead time + service
 * level inputs recompute the forecast decision. Never influences ranking.
 */
export function SafetyStockPanel({
  decision,
  leadTimeDays,
  serviceLevel,
  isRecomputing,
  onLeadTimeChange,
  onServiceLevelChange,
  onRecompute,
}: SafetyStockPanelProps) {
  return (
    <Card data-testid="safety-stock-panel">
      <CardHeader>
        <CardTitle>{SAFETY_STOCK_HEADER}</CardTitle>
        <CardDescription>
          A deterministic reorder heuristic (demand variability only, constant lead
          time). Adjust the inputs and recompute.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="space-y-1">
            <span className="text-xs text-muted-foreground">Lead time (days)</span>
            <Input
              type="number"
              min={1}
              max={365}
              value={String(leadTimeDays)}
              onChange={(event) => onLeadTimeChange(Number(event.target.value) || 0)}
              className="w-32"
              data-testid="safety-stock-lead-time"
            />
          </div>
          <div className="space-y-1">
            <span className="text-xs text-muted-foreground">Service level</span>
            <Select
              value={String(serviceLevel)}
              onValueChange={(value) => onServiceLevelChange(Number(value))}
            >
              <SelectTrigger className="w-32" data-testid="safety-stock-service-level">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SERVICE_LEVEL_OPTIONS.map((level) => (
                  <SelectItem key={level} value={String(level)}>
                    {(level * 100).toFixed(level === 0.975 ? 1 : 0)}%
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button
            type="button"
            variant="secondary"
            onClick={onRecompute}
            disabled={isRecomputing}
            data-testid="safety-stock-recompute"
          >
            {isRecomputing ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-2 h-4 w-4" />
            )}
            Recompute
          </Button>
        </div>

        {decision && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="z value" value={decision.z_value.toFixed(4)} />
            <Stat label="σ daily" value={decision.sigma_daily_demand.toFixed(2)} />
            <Stat label="Safety stock" value={decision.safety_stock.toFixed(1)} />
            <Stat label="Reorder point" value={decision.reorder_point.toFixed(1)} />
          </div>
        )}
      </CardContent>
    </Card>
  )
}
