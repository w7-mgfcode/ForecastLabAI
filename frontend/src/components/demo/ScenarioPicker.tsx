import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { ScenarioPreset } from '@/types/api'

interface ScenarioOption {
  value: ScenarioPreset
  title: string
  description: string
  estimatedWallClock: string
  caveat?: string
  caveatKind?: 'expected-skip' | 'info'
}

// E2 (#391) — single source of card copy. Descriptions are truthful to the
// demo-scaled _SeedProfile the pipeline's seed step posts
// (app/features/demo/pipeline.py:_SCENARIO_SEED_PROFILE), NOT to the preset's
// native full-size config.
const SCENARIO_OPTIONS: ScenarioOption[] = [
  {
    value: 'demo_minimal',
    title: 'Demo minimal',
    description: '3 stores × 10 products × 92 days — fast smoke loop',
    estimatedWallClock: '~60 s',
  },
  {
    value: 'showcase_rich',
    title: 'Showcase rich',
    description: '5 × 15 × 180 days — full 24-step flow, V1+V2 modeling',
    estimatedWallClock: '~3 min',
    caveat: 'Knowledge/agent steps skip without provider keys',
    caveatKind: 'info',
  },
  {
    value: 'retail_standard',
    title: 'Retail standard',
    description: '5 × 15 × 180 days — steady demand, light promos',
    estimatedWallClock: '~90 s',
  },
  {
    value: 'holiday_rush',
    title: 'Holiday rush',
    description: '5 × 15 × Oct–Dec 2024 — Black Friday/Christmas spikes',
    estimatedWallClock: '~90 s',
    caveat: 'Seeds a pinned 2024 window (calendar-pinned holidays)',
    caveatKind: 'info',
  },
  {
    value: 'high_variance',
    title: 'High variance',
    description: '5 × 15 × 180 days — noisy demand with anomaly spikes',
    estimatedWallClock: '~90 s',
  },
  {
    value: 'stockout_heavy',
    title: 'Stockout heavy',
    description: '5 × 15 × 180 days — 25% stockout days zero the sales',
    estimatedWallClock: '~90 s',
  },
  {
    value: 'new_launches',
    title: 'New launches',
    description: '5 × 25 × 180 days — 45-day product launch ramps',
    estimatedWallClock: '~2 min',
  },
  {
    value: 'sparse',
    title: 'Sparse',
    description: '3 × 10 × 92 days — 50% missing grains + random gaps',
    estimatedWallClock: '~90 s',
    caveat: '⏭️ May fail at features/backtest (NaN WAPE) — expected; see runbook',
    caveatKind: 'expected-skip',
  },
]

interface ScenarioPickerProps {
  value: ScenarioPreset
  onChange: (value: ScenarioPreset) => void
  disabled?: boolean
}

/**
 * E2 (#391) — guided card grid for the demo pipeline's scenario preset.
 *
 * All 8 backend ScenarioPreset values are exposed as aria-pressed toggle
 * buttons (W3C APG button pattern — no roving tabindex needed, unlike
 * role="radio"). Default `demo_minimal` keeps wire-compat with prior clients.
 */
export function ScenarioPicker({ value, onChange, disabled }: ScenarioPickerProps) {
  return (
    <div className="flex flex-col gap-2">
      <label className="text-sm font-medium">Scenario</label>
      <div role="group" aria-label="Scenario" className="grid grid-cols-2 gap-2 xl:grid-cols-4">
        {SCENARIO_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            aria-pressed={opt.value === value}
            disabled={disabled}
            onClick={() => onChange(opt.value)}
            className={cn(
              'rounded-lg border p-3 text-left transition-colors',
              'hover:bg-muted/50 disabled:pointer-events-none disabled:opacity-50',
              opt.value === value ? 'border-primary ring-1 ring-primary' : 'border-border'
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-medium">{opt.title}</span>
              <span className="font-mono text-xs text-muted-foreground">{opt.value}</span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {opt.description} · {opt.estimatedWallClock}
            </p>
            {opt.caveat && (
              <Badge variant="outline" className="mt-2 whitespace-normal text-xs text-muted-foreground">
                {opt.caveat}
              </Badge>
            )}
          </button>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        Tick <span className="font-medium">Re-seed first</span> when switching presets — without
        it the run reuses the currently seeded dataset.
      </p>
    </div>
  )
}
