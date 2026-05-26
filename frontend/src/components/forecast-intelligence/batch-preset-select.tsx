import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { BATCH_PRESETS, type BatchPresetId } from './batch-preset-utils'

/**
 * PRP-37 Slice C — five hardcoded batch sweep presets surfaced as a Select.
 * Each preset emits a list of `BatchModelConfig` rows (via the sibling
 * `buildPresetConfigs` helper); the parent translates the rows into a
 * BatchSubmitRequest.
 */

interface BatchPresetSelectProps {
  value?: BatchPresetId
  onChange: (preset: BatchPresetId) => void
  className?: string
  disabled?: boolean
}

export function BatchPresetSelect({
  value,
  onChange,
  className,
  disabled,
}: BatchPresetSelectProps) {
  return (
    <Select
      value={value}
      onValueChange={(next) => onChange(next as BatchPresetId)}
      disabled={disabled}
    >
      <SelectTrigger
        className={className ?? 'w-[280px]'}
        data-testid="batch-preset-trigger"
      >
        <SelectValue placeholder="Pick a preset…" />
      </SelectTrigger>
      <SelectContent>
        {BATCH_PRESETS.map((preset) => (
          <SelectItem key={preset.id} value={preset.id}>
            {preset.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
