import { LoadingState } from '@/components/common/loading-state'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { cn } from '@/lib/utils'
import type { CandidateModelInfo, ModelCatalogResponse, ModelFamily } from '@/types/api'

/** Backend caps `candidate_models` at 10 (ModelSelectionRunRequest.max_length). */
export const MAX_CANDIDATES = 10

interface CandidateModelPickerProps {
  catalog?: ModelCatalogResponse
  selected: string[]
  onChange: (types: string[]) => void
  isLoading: boolean
}

const FAMILY_ORDER: ModelFamily[] = ['baseline', 'additive', 'tree']
const FAMILY_LABEL: Record<ModelFamily, string> = {
  baseline: 'Baseline',
  additive: 'Additive',
  tree: 'Tree-based',
}

/**
 * Candidate-model multi-select fed by the BACKEND catalog (never the hardcoded
 * `model-type-utils`). Mirrors the batch-matrix-picker conventions: a checkbox
 * per model grouped by family, opt-in-extra + feature-aware badges, and a
 * selection cap of 10.
 */
export function CandidateModelPicker({
  catalog,
  selected,
  onChange,
  isLoading,
}: CandidateModelPickerProps) {
  if (isLoading) {
    return <LoadingState message="Loading models…" />
  }
  if (!catalog || catalog.models.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">No models available.</p>
    )
  }

  const selectedSet = new Set(selected)
  const atCap = selected.length >= MAX_CANDIDATES

  function toggle(modelType: string) {
    if (selectedSet.has(modelType)) {
      onChange(selected.filter((type) => type !== modelType))
    } else if (!atCap) {
      onChange([...selected, modelType])
    }
  }

  const byFamily = new Map<ModelFamily, CandidateModelInfo[]>()
  for (const model of catalog.models) {
    const list = byFamily.get(model.family) ?? []
    list.push(model)
    byFamily.set(model.family, list)
  }

  return (
    <div className="space-y-4" data-testid="candidate-model-picker">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">
          {selected.length} of {MAX_CANDIDATES} selected
        </span>
        {atCap && (
          <Badge variant="secondary" data-testid="candidate-cap-badge">
            Max {MAX_CANDIDATES} reached
          </Badge>
        )}
      </div>

      {FAMILY_ORDER.filter((family) => byFamily.has(family)).map((family) => (
        <div key={family} className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {FAMILY_LABEL[family]}
          </p>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {(byFamily.get(family) ?? []).map((model) => {
              const isSelected = selectedSet.has(model.model_type)
              const disabled = !isSelected && atCap
              return (
                <label
                  key={model.model_type}
                  data-testid={`candidate-model-${model.model_type}`}
                  className={cn(
                    'flex cursor-pointer items-start gap-3 rounded-md border p-3 transition-colors',
                    isSelected && 'border-primary bg-primary/5',
                    disabled && 'cursor-not-allowed opacity-50',
                  )}
                >
                  <Checkbox
                    checked={isSelected}
                    disabled={disabled}
                    data-testid={`candidate-checkbox-${model.model_type}`}
                    onCheckedChange={() => toggle(model.model_type)}
                    className="mt-0.5"
                  />
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-sm font-medium">{model.label}</span>
                      {model.requires_extra && (
                        <Badge
                          variant="outline"
                          data-testid={`candidate-extra-badge-${model.model_type}`}
                        >
                          extra
                        </Badge>
                      )}
                      {model.feature_aware && (
                        <Badge variant="outline">feature-aware</Badge>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {model.description}
                    </p>
                  </div>
                </label>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}
