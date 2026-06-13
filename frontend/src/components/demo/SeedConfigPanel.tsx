import { useState } from 'react'
import { ChevronsUpDown, AlertTriangle } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { Input } from '@/components/ui/input'
import { Slider } from '@/components/ui/slider'
import type { SeedOverrides } from '@/types/api'

/**
 * E3 (#409) — advanced seed config panel: the 7 curated, allow-listed knobs.
 *
 * Emits a SPARSE object (only operator-touched knobs) and null when nothing
 * is set, so legacy start frames stay byte-identical. The UI int ranges are
 * deliberately TIGHTER than the API bounds (laptop-scale demo data); the API
 * bounds are the law and the backend rejects anything outside them.
 */
interface SeedConfigPanelProps {
  value: SeedOverrides | null
  onChange: (value: SeedOverrides | null) => void
  /** Disable every control (run in flight / Re-seed unticked). */
  disabled?: boolean
  /** holiday_rush is calendar-pinned — the window control locks. */
  windowLocked?: boolean
}

// UI input ranges (int knobs). API bounds: stores 1..100, products 1..500,
// window_days 75..365 — the inputs clamp to demo-scale subsets.
const INT_KNOBS = [
  { key: 'stores', label: 'Stores', min: 1, max: 20, placeholder: 'preset' },
  { key: 'products', label: 'Products', min: 1, max: 50, placeholder: 'preset' },
  { key: 'window_days', label: 'Window (days)', min: 75, max: 365, placeholder: 'preset' },
] as const

// Float knobs rendered as sliders. API bounds are the slider ranges.
const FLOAT_KNOBS = [
  { key: 'sparsity', label: 'Sparsity', max: 0.9 },
  { key: 'promotion_intensity', label: 'Promotion intensity', max: 0.5 },
  { key: 'stockout_intensity', label: 'Stockout intensity', max: 0.5 },
  { key: 'noise_sigma', label: 'Noise sigma', max: 0.5 },
] as const

/** Thresholds above which the NaN-WAPE caveat shows (mirrors the sparse
 *  preset's documented expected-fail semantics, RUNBOOKS incident 28). */
const RISKY_SPARSITY = 0.4
const RISKY_STOCKOUT = 0.25

function setKnob(
  value: SeedOverrides | null,
  key: keyof SeedOverrides,
  knobValue: number | undefined
): SeedOverrides | null {
  const next: SeedOverrides = { ...(value ?? {}) }
  if (knobValue === undefined) {
    delete next[key]
  } else {
    next[key] = knobValue
  }
  return Object.keys(next).length > 0 ? next : null
}

export function SeedConfigPanel({
  value,
  onChange,
  disabled = false,
  windowLocked = false,
}: SeedConfigPanelProps) {
  const [open, setOpen] = useState(false)

  const touched = value !== null && Object.keys(value).length > 0
  const risky =
    (value?.sparsity ?? 0) > RISKY_SPARSITY || (value?.stockout_intensity ?? 0) > RISKY_STOCKOUT

  const summaryParts: string[] = []
  if (value?.stores !== undefined) summaryParts.push(`${value.stores} stores`)
  if (value?.products !== undefined) summaryParts.push(`${value.products} products`)
  if (value?.window_days !== undefined) summaryParts.push(`${value.window_days} days`)
  if (value?.sparsity !== undefined) summaryParts.push(`sparsity ${value.sparsity.toFixed(2)}`)
  if (value?.promotion_intensity !== undefined)
    summaryParts.push(`promo ${value.promotion_intensity.toFixed(2)}`)
  if (value?.stockout_intensity !== undefined)
    summaryParts.push(`stockout ${value.stockout_intensity.toFixed(2)}`)
  if (value?.noise_sigma !== undefined)
    summaryParts.push(`noise ${value.noise_sigma.toFixed(2)}`)

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="w-full">
      <CollapsibleTrigger asChild>
        {/* The trigger stays clickable while disabled so the operator can
            still INSPECT the config mid-run; only the controls lock. */}
        <Button variant="ghost" size="sm" className="gap-2 px-2">
          <ChevronsUpDown data-icon="inline-start" />
          Advanced seed config
          {touched && (
            <Badge variant="secondary">
              {Object.keys(value ?? {}).length} knob{Object.keys(value ?? {}).length > 1 && 's'}
            </Badge>
          )}
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="mt-2 flex flex-col gap-4 rounded-md border p-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {INT_KNOBS.map((knob) => {
              const locked = knob.key === 'window_days' && windowLocked
              return (
                <label key={knob.key} className="flex flex-col gap-1 text-sm">
                  <span className="text-xs text-muted-foreground">
                    {knob.label}{' '}
                    <span className="text-muted-foreground/70">
                      ({knob.min}–{knob.max})
                    </span>
                  </span>
                  <Input
                    type="number"
                    aria-label={knob.label}
                    min={knob.min}
                    max={knob.max}
                    placeholder={knob.placeholder}
                    className="h-9"
                    value={value?.[knob.key] ?? ''}
                    disabled={disabled || locked}
                    title={
                      locked
                        ? 'holiday_rush seeds a calendar-pinned 2024 window — the window length cannot be overridden'
                        : undefined
                    }
                    onChange={(e) => {
                      const raw = e.target.value
                      if (raw === '') {
                        onChange(setKnob(value, knob.key, undefined))
                        return
                      }
                      const parsed = Number.parseInt(raw, 10)
                      if (Number.isNaN(parsed)) return
                      onChange(setKnob(value, knob.key, parsed))
                    }}
                  />
                  {locked && (
                    <span className="text-xs text-muted-foreground">
                      pinned window (holiday_rush)
                    </span>
                  )}
                </label>
              )
            })}
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {FLOAT_KNOBS.map((knob) => {
              const knobValue = value?.[knob.key]
              return (
              <div key={knob.key} className="flex flex-col gap-1 text-sm">
                <span className="text-xs text-muted-foreground">
                  {knob.label}:{' '}
                  <span className="font-mono">
                    {knobValue !== undefined ? knobValue.toFixed(2) : 'preset'}
                  </span>
                </span>
                <Slider
                  aria-label={knob.label}
                  min={0}
                  max={knob.max}
                  step={0.05}
                  value={[knobValue ?? 0]}
                  disabled={disabled}
                  onValueChange={(vals) => {
                    const v = vals[0]
                    // 0 from an untouched slider means "preset" — only an
                    // explicit non-zero (or a previously set knob) registers.
                    if (v === 0 && knobValue === undefined) return
                    onChange(setKnob(value, knob.key, v === 0 ? undefined : v))
                  }}
                />
              </div>
              )
            })}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {touched ? (
              <>
                <p className="text-sm text-muted-foreground">{summaryParts.join(' · ')}</p>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={disabled}
                  onClick={() => onChange(null)}
                >
                  Clear overrides
                </Button>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                No overrides — the scenario preset drives every knob.
              </p>
            )}
            {risky && (
              <Badge variant="outline" className="gap-1 text-destructive">
                <AlertTriangle data-icon="inline-start" />
                high sparsity/stockout can legitimately fail the backtest (NaN WAPE)
              </Badge>
            )}
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}
