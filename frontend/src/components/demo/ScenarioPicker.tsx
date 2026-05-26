import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { ScenarioPreset } from '@/types/api'

interface ScenarioOption {
  value: ScenarioPreset
  label: string
  description: string
  estimatedWallClock: string
}

const SCENARIO_OPTIONS: ScenarioOption[] = [
  {
    value: 'demo_minimal',
    label: 'demo_minimal',
    description: '3 stores × 10 products × 92 days — fast smoke loop',
    estimatedWallClock: '~60 s',
  },
  {
    value: 'showcase_rich',
    label: 'showcase_rich',
    description: '5 stores × 15 products × 180 days — V1+V2 modeling',
    estimatedWallClock: '~3 min',
  },
  {
    value: 'sparse',
    label: 'sparse',
    description: 'Sparse + gappy time series — edge-case data shape',
    estimatedWallClock: '~90 s',
  },
]

interface ScenarioPickerProps {
  value: ScenarioPreset
  onChange: (value: ScenarioPreset) => void
  disabled?: boolean
}

/**
 * PRP-38 — shadcn `<Select>` for the demo pipeline's scenario preset.
 *
 * Composition rule: `<SelectItem>` lives inside `<SelectGroup>` per
 * `.claude/rules/shadcn-ui.md`. Three headline options; default
 * `demo_minimal` keeps wire-compat with prior clients.
 */
export function ScenarioPicker({ value, onChange, disabled }: ScenarioPickerProps) {
  return (
    <div className="flex flex-col gap-2">
      <label className="text-sm font-medium">Scenario</label>
      <Select
        value={value}
        onValueChange={(v) => onChange(v as ScenarioPreset)}
        disabled={disabled}
      >
        <SelectTrigger className="w-[280px]">
          <SelectValue placeholder="Pick a scenario" />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            {SCENARIO_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                <div className="flex flex-col">
                  <span className="font-mono">{opt.label}</span>
                  <span className="text-xs text-muted-foreground">
                    {opt.description} · {opt.estimatedWallClock}
                  </span>
                </div>
              </SelectItem>
            ))}
          </SelectGroup>
        </SelectContent>
      </Select>
    </div>
  )
}
