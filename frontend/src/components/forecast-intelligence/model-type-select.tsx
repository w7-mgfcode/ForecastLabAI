import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { ModelFamily } from '@/types/api'
import {
  MODEL_TYPE_LABELS,
  modelsForFamily,
} from './model-type-utils'

/**
 * PRP-37 Slice C — model-type Select filtered by family. Mirrors backend
 * `_MODEL_FAMILY_MAP` (app/features/forecasting/feature_metadata.py). When
 * a value falls outside the picked family, the parent component is
 * responsible for resetting it — this component does NOT silently reset.
 */

interface ModelTypeSelectProps {
  family: ModelFamily
  value: string
  onChange: (modelType: string) => void
  /** Optional restriction set — usually the runtime-confirmed model list. */
  availableModels?: string[]
  disabled?: boolean
  className?: string
}

export function ModelTypeSelect({
  family,
  value,
  onChange,
  availableModels,
  disabled,
  className,
}: ModelTypeSelectProps) {
  const options = modelsForFamily(family, availableModels)
  return (
    <Select
      value={value}
      onValueChange={onChange}
      disabled={disabled || options.length === 0}
    >
      <SelectTrigger
        className={className}
        data-testid={`model-type-select-trigger-${family}`}
      >
        <SelectValue placeholder="Pick a model…" />
      </SelectTrigger>
      <SelectContent>
        {options.map((modelType) => (
          <SelectItem key={modelType} value={modelType}>
            {MODEL_TYPE_LABELS[modelType] ?? modelType}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
