import { useMemo, useState } from 'react'
import { ChevronDown, RotateCcw, SlidersHorizontal } from 'lucide-react'
import { CandidateModelPicker } from '@/components/champion-selector/candidate-model-picker'
import { useModelCatalog } from '@/hooks/use-model-selection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'
import type {
  DemoBacktestConfig,
  ModelCatalogResponse,
  ModelFamily,
  ScenarioPreset,
} from '@/types/api'
import { DemoBacktestSettingsForm } from './DemoBacktestSettingsForm'
import {
  DEFAULT_BACKTEST,
  DEFAULT_TRAIN_MODELS,
  buildTrainPlan,
  isDefaultBacktest,
  isDefaultSelection,
} from './run-config-utils'

interface RunConfigPanelProps {
  scenario: ScenarioPreset
  disabled?: boolean
  selection: string[]
  onSelectionChange: (models: string[]) => void
  backtest: DemoBacktestConfig
  onBacktestChange: (cfg: DemoBacktestConfig) => void
}

/**
 * E4 (#410) — collapsible "Run configuration (advanced)" section on /showcase.
 *
 * Composes the reused CandidateModelPicker (fed an enabled-filtered catalog so
 * disabled opt-in models are hidden), the DemoBacktestSettingsForm, a Reset
 * button, and a train-candidate preview chip list. Collapsed by default so an
 * untouched run sends a byte-identical legacy frame (the dirty-only rule lives
 * in showcase.tsx).
 */
export function RunConfigPanel({
  scenario,
  disabled = false,
  selection,
  onSelectionChange,
  backtest,
  onBacktestChange,
}: RunConfigPanelProps) {
  const [open, setOpen] = useState(false)
  const { data: catalog, isLoading } = useModelCatalog()

  // Hide opt-in models whose forecast_enable_* flag is off (catalog.enabled).
  const enabledCatalog: ModelCatalogResponse | undefined = useMemo(() => {
    if (!catalog) return undefined
    return { ...catalog, models: catalog.models.filter((m) => m.enabled) }
  }, [catalog])

  const familyByType = useMemo(() => {
    const map: Record<string, ModelFamily> = {}
    for (const m of catalog?.models ?? []) map[m.model_type] = m.family
    return map
  }, [catalog])

  const plan = useMemo(
    () => buildTrainPlan(selection, scenario, familyByType),
    [selection, scenario, familyByType],
  )

  const isCustomized = !isDefaultSelection(selection) || !isDefaultBacktest(backtest)

  function reset() {
    onSelectionChange([...DEFAULT_TRAIN_MODELS])
    onBacktestChange({ ...DEFAULT_BACKTEST })
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen} data-testid="run-config-panel">
      <CollapsibleTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          data-testid="run-config-toggle"
          disabled={disabled}
        >
          <SlidersHorizontal className="mr-2 h-4 w-4" />
          Run configuration (advanced)
          {isCustomized && (
            <Badge variant="secondary" className="ml-2" data-testid="run-config-custom-badge">
              customized
            </Badge>
          )}
          <ChevronDown
            className={cn('ml-2 h-4 w-4 transition-transform', open && 'rotate-180')}
          />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-6 pt-4">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium">Models to train</p>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              data-testid="run-config-reset"
              onClick={reset}
              disabled={disabled}
            >
              <RotateCcw className="mr-2 h-4 w-4" />
              Reset to defaults
            </Button>
          </div>
          <CandidateModelPicker
            catalog={enabledCatalog}
            selected={selection}
            onChange={onSelectionChange}
            isLoading={isLoading}
          />
        </div>

        <div className="space-y-2">
          <p className="text-sm font-medium">Backtest settings</p>
          <DemoBacktestSettingsForm
            value={backtest}
            scenario={scenario}
            onChange={onBacktestChange}
            disabled={disabled}
          />
        </div>

        <div className="space-y-2" data-testid="train-candidate-preview">
          <p className="text-sm font-medium">
            Will train {plan.length} model{plan.length === 1 ? '' : 's'}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {plan.map((entry) => (
              <Badge
                key={entry.model_type}
                variant={entry.v2 ? 'default' : 'outline'}
                data-testid={`preview-chip-${entry.model_type}`}
              >
                {entry.model_type}
                {entry.v2 ? ' (V2)' : ''}
                {entry.family ? ` · ${entry.family}` : ''}
              </Badge>
            ))}
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}
