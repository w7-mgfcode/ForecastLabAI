import { useState } from 'react'
import { ChevronDown, Settings2 } from 'lucide-react'
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
import { splitConfigErrors } from '@/components/champion-selector/split-config'
import { cn } from '@/lib/utils'
import type {
  DemoBacktestConfig,
  DemoRankingMetric,
  ScenarioPreset,
  SplitStrategy,
} from '@/types/api'
import { splitFitWarning } from './run-config-utils'

interface DemoBacktestSettingsFormProps {
  value: DemoBacktestConfig
  scenario: ScenarioPreset
  onChange: (next: DemoBacktestConfig) => void
  disabled?: boolean
}

const RANKING_METRICS: { value: DemoRankingMetric; label: string }[] = [
  { value: 'wape', label: 'WAPE (default)' },
  { value: 'mae', label: 'MAE' },
  { value: 'rmse', label: 'RMSE' },
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
 * E4 (#410) — showcase backtest-settings form. Mirrors the champion selector's
 * BacktestSettingsForm, with two intentional differences: the horizon is
 * EDITABLE here (the showcase drives its own horizon), and the metric list is
 * WAPE/MAE/RMSE (issue #410). A non-blocking split-fit warning surfaces when
 * the chosen split cannot fit the scenario's seeded window.
 */
export function DemoBacktestSettingsForm({
  value,
  scenario,
  onChange,
  disabled = false,
}: DemoBacktestSettingsFormProps) {
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const errors = splitConfigErrors(value)
  const fitWarning = splitFitWarning(value, scenario)

  function patch(partial: Partial<DemoBacktestConfig>) {
    onChange({ ...value, ...partial })
  }

  return (
    <div className="space-y-4" data-testid="demo-backtest-settings-form">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Ranking metric" hint="Lower is better. Picks the winning model.">
          <Select
            value={value.metric}
            onValueChange={(metric) => patch({ metric: metric as DemoRankingMetric })}
            disabled={disabled}
          >
            <SelectTrigger data-testid="demo-ranking-metric-select">
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
        <Field label="Horizon (1–90 days)" hint="Forecast length each fold evaluates.">
          <Input
            type="number"
            min={1}
            max={90}
            value={String(value.horizon)}
            data-testid="demo-settings-horizon"
            disabled={disabled}
            onChange={(event) => patch({ horizon: Number(event.target.value) || 0 })}
          />
        </Field>
      </div>

      <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
        <CollapsibleTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            data-testid="demo-advanced-toggle"
            disabled={disabled}
          >
            <Settings2 className="mr-2 h-4 w-4" />
            Advanced split settings
            <ChevronDown
              className={cn('ml-2 h-4 w-4 transition-transform', advancedOpen && 'rotate-180')}
            />
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent className="pt-3">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Strategy">
              <Select
                value={value.strategy}
                onValueChange={(strategy) => patch({ strategy: strategy as SplitStrategy })}
                disabled={disabled}
              >
                <SelectTrigger data-testid="demo-settings-strategy">
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
                data-testid="demo-settings-n-splits"
                disabled={disabled}
                onChange={(event) => patch({ n_splits: Number(event.target.value) || 0 })}
              />
            </Field>
            <Field label="Min train (≥7d)">
              <Input
                type="number"
                min={7}
                value={String(value.min_train_size)}
                data-testid="demo-settings-min-train"
                disabled={disabled}
                onChange={(event) => patch({ min_train_size: Number(event.target.value) || 0 })}
              />
            </Field>
            <Field label="Gap (0–30d)">
              <Input
                type="number"
                min={0}
                max={30}
                value={String(value.gap)}
                data-testid="demo-settings-gap"
                disabled={disabled}
                onChange={(event) => patch({ gap: Number(event.target.value) || 0 })}
              />
            </Field>
          </div>
        </CollapsibleContent>
      </Collapsible>

      {errors.length > 0 && (
        <ul className="space-y-0.5" data-testid="demo-settings-errors">
          {errors.map((error) => (
            <li key={error} className="text-xs text-destructive">
              {error}
            </li>
          ))}
        </ul>
      )}

      {fitWarning && (
        <p className="text-xs text-amber-600 dark:text-amber-500" data-testid="demo-split-fit-warning">
          {fitWarning}
        </p>
      )}
    </div>
  )
}
