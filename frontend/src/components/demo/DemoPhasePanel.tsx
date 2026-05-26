import { useEffect, useState } from 'react'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'
import { DemoStepCard } from './demo-step-card'
import { PHASE_LABEL } from './PHASE_DEFS'
import type { DemoStep } from '@/hooks/use-demo-pipeline'

const TERMINAL_STATUSES = new Set(['pass', 'fail', 'skip', 'warn'])

interface PhaseGroup {
  id: string
  label: string
  steps: DemoStep[]
}

interface DemoPhasePanelProps {
  phases: PhaseGroup[]
  /** Id of the currently-running phase — drives auto-expansion. */
  runningPhase?: string | null
  /** Per-step Inspect href resolver; return null to hide the button. */
  getInspectHref?: (step: DemoStep) => string | null
}

/**
 * PRP-38 — shadcn `<Accordion>` grouping demo step cards by phase.
 *
 * The accordion is controlled by `runningPhase`: when the pipeline moves
 * into a new phase, that phase auto-expands. Completed phases collapse so
 * a 14-step run stays scannable.
 */
export function DemoPhasePanel({
  phases,
  runningPhase,
  getInspectHref,
}: DemoPhasePanelProps) {
  // PRP-41 / issue #311 — controlled accordion needs an onValueChange handler.
  // Without it, the parent's recomputed `value` overrides every user click,
  // pinning the open panel to the running/fallback phase. Lift to local
  // state and let `useEffect` re-sync only when the parent's hint moves.
  const fallback = phases.find((p) => p.steps.some((s) => s.status === 'running'))?.id
  const computedValue = runningPhase ?? fallback ?? phases[0]?.id ?? ''
  const [expandedPhase, setExpandedPhase] = useState<string>(computedValue)
  useEffect(() => {
    setExpandedPhase(computedValue)
  }, [computedValue])

  return (
    <Accordion
      type="single"
      collapsible
      value={expandedPhase}
      onValueChange={setExpandedPhase}
      className="space-y-2"
    >
      {phases.map((phase, phaseIndex) => {
        const completed = phase.steps.filter((s) => TERMINAL_STATUSES.has(s.status)).length
        return (
          <AccordionItem
            key={phase.id}
            value={phase.id}
            className="rounded-md border bg-card"
          >
            <AccordionTrigger className="px-4 py-3">
              <div className="flex w-full items-center justify-between gap-3">
                <span className="font-semibold">
                  <span className="mr-2 text-muted-foreground">
                    {String(phaseIndex + 1).padStart(2, '0')}.
                  </span>
                  {PHASE_LABEL[phase.id] ?? phase.label}
                </span>
                <span className="font-mono text-xs text-muted-foreground">
                  {completed}/{phase.steps.length}
                </span>
              </div>
            </AccordionTrigger>
            <AccordionContent className="px-4 pb-3">
              <div className="space-y-2">
                {phase.steps.map((step, index) => (
                  <DemoStepCard
                    key={step.name}
                    step={step}
                    index={index}
                    inspectHref={getInspectHref?.(step) ?? null}
                  />
                ))}
              </div>
            </AccordionContent>
          </AccordionItem>
        )
      })}
    </Accordion>
  )
}
