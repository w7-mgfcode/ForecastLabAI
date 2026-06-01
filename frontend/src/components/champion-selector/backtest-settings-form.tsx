import { useState } from 'react'
import { ChevronDown, Settings2, Wand2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import type { RankingMetric, SplitConfig, SplitStrategy } from '@/types/api'
import { BIAS_EXPLANATION, RANKING_TIE_BREAK } from './copy'
import { splitConfigErrors } from './split-config'

interface BacktestSettingsFormProps {
  value: SplitConfig
  rankingMetric: RankingMetric
  forecastHorizon: number
  onChange: (next: SplitConfig) => void
  onRankingMetricChange: (metric: RankingMetric) => void
  recommended?: SplitConfig
}

const RANKING_METRICS: { value: RankingMetric; label: string }[] = [
  { value: 'wape', label: 'WAPE (default)' },
  { value: 'smape', label: 'sMAPE' },
  { value: 'mae', label: 'MAE' },
  { value: 'bias', label: 'Bias' },
]

function Field({
  label,
  children,
  hint,
}: {
  label: string
  children: React.ReactNode
  hint?: string
}) {
  return (
    <div className="space-y-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      {children}
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  )
}

/**
 * Simple/advanced backtest-settings form. The horizon is DERIVED from
 * `forecastHorizon` (kept equal so the assembled run request is always valid)
 * and shown read-only. The advanced toggle reveals the split-CV knobs.
 */
export function BacktestSettingsForm({
  value,
  rankingMetric,
  forecastHorizon,
  onChange,
  onRankingMetricChange,
  recommended,
}: BacktestSettingsFormProps) {
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const errors = splitConfigErrors(value)

  function patch(partial: Partial<SplitConfig>) {
    onChange({ ...value, ...partial, horizon: forecastHorizon })
  }

  return (
    <div className="space-y-4" data-testid="backtest-settings-form">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Ranking metric" hint={`${RANKING_TIE_BREAK} ${BIAS_EXPLANATION}`}>
          <Select
            value={rankingMetric}
            onValueChange={(metric) => onRankingMetricChange(metric as RankingMetric)}
          >
            <SelectTrigger data-testid="ranking-metric-select">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {RANKING_METRICS.map((metric) => (
                <SelectItem key={metric.value} value={metric.value}>
                  {metric.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field
          label="Horizon (days)"
          hint="Locked to the forecast horizon above so the backtest matches the forecast."
        >
          <Input
            type="number"
            value={String(forecastHorizon)}
            readOnly
            disabled
            data-testid="settings-horizon"
          />
        </Field>
      </div>

      {recommended && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          data-testid="use-recommended-split"
          onClick={() =>
            onChange({ ...recommended, horizon: forecastHorizon })
          }
        >
          <Wand2 className="mr-2 h-4 w-4" />
          Use recommended split
        </Button>
      )}

      <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
        <CollapsibleTrigger asChild>
          <Button type="button" variant="ghost" size="sm" data-testid="advanced-toggle">
            <Settings2 className="mr-2 h-4 w-4" />
            Advanced split settings
            <ChevronDown
              className={cn(
                'ml-2 h-4 w-4 transition-transform',
                advancedOpen && 'rotate-180',
              )}
            />
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent className="pt-3">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Strategy">
              <Select
                value={value.strategy}
                onValueChange={(strategy) =>
                  patch({ strategy: strategy as SplitStrategy })
                }
              >
                <SelectTrigger data-testid="settings-strategy">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="expanding">Expanding</SelectItem>
                  <SelectItem value="sliding">Sliding</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field label="Splits (2–20)">
              <Input
                type="number"
                min={2}
                max={20}
                value={String(value.n_splits)}
                data-testid="settings-n-splits"
                onChange={(event) =>
                  patch({ n_splits: Number(event.target.value) || 0 })
                }
              />
            </Field>
            <Field label="Min train (≥7d)">
              <Input
                type="number"
                min={7}
                value={String(value.min_train_size)}
                data-testid="settings-min-train"
                onChange={(event) =>
                  patch({ min_train_size: Number(event.target.value) || 0 })
                }
              />
            </Field>
            <Field label="Gap (0–30d)">
              <Input
                type="number"
                min={0}
                max={30}
                value={String(value.gap)}
                data-testid="settings-gap"
                onChange={(event) =>
                  patch({ gap: Number(event.target.value) || 0 })
                }
              />
            </Field>
          </div>
        </CollapsibleContent>
      </Collapsible>

      {errors.length > 0 && (
        <ul className="space-y-0.5" data-testid="settings-errors">
          {errors.map((error) => (
            <li key={error} className="text-xs text-destructive">
              {error}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
