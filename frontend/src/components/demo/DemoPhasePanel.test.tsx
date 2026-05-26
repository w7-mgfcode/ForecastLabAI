/**
 * PRP-41 / issue #311 — DemoPhasePanel onValueChange test.
 *
 * Verifies the controlled Accordion's open panel:
 *   1. Initially derives from `runningPhase` (or the first phase).
 *   2. Tracks `runningPhase` updates while the pipeline is in flight.
 *   3. Honours user clicks AFTER pipeline_complete (runningPhase=null)
 *      without snapping back to the running/fallback fallback chain.
 */

import { cleanup, fireEvent, render } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { useState } from 'react'
import { DemoPhasePanel } from './DemoPhasePanel'
import type { DemoStep } from '@/hooks/use-demo-pipeline'

afterEach(() => {
  cleanup()
})

const makeStep = (
  name: string,
  status: DemoStep['status'] = 'idle',
  overrides: Partial<DemoStep> = {},
): DemoStep => ({
  name,
  label: name,
  status,
  detail: '',
  durationMs: 0,
  data: {},
  phaseName: 'data',
  ...overrides,
})

describe('DemoPhasePanel (#311 onValueChange fix)', () => {
  // Radix Accordion renders each AccordionItem with a `data-state` attribute.
  // To avoid ambiguity in accessible-name matching (header text includes the
  // numeric index "01.", "02.", ...), we resolve the open trigger via the
  // aria-expanded attribute and read the inner label span text.
  const openPhaseLabel = (container: HTMLElement): string | null => {
    const trigger = container.querySelector('button[aria-expanded="true"]')
    if (!trigger) return null
    // The label span is the .font-semibold child; its first sub-span carries
    // the index prefix; the trailing text node is the phase label.
    const labelSpan = trigger.querySelector('span.font-semibold')
    if (!labelSpan) return null
    // Extract direct text-node content (skips the inner index span).
    let label = ''
    labelSpan.childNodes.forEach((node) => {
      if (node.nodeType === Node.TEXT_NODE) {
        label += node.textContent ?? ''
      }
    })
    return label.trim() || null
  }

  it('opens the running phase initially', () => {
    const phases = [
      { id: 'data', label: 'Data', steps: [makeStep('precheck', 'pass')] },
      { id: 'modeling', label: 'Modeling', steps: [makeStep('train', 'running')] },
      { id: 'verify', label: 'Verify', steps: [makeStep('verify')] },
    ]
    const { container } = render(<DemoPhasePanel phases={phases} runningPhase="modeling" />)
    expect(openPhaseLabel(container)).toBe('Modeling')
  })

  it('lets the user expand any phase after pipeline_complete without snapping back', () => {
    function Harness() {
      const [running] = useState<string | null>(null)
      const phases = [
        { id: 'data', label: 'Data', steps: [makeStep('precheck', 'pass')] },
        { id: 'verify', label: 'Verify', steps: [makeStep('verify', 'pass')] },
      ]
      return <DemoPhasePanel phases={phases} runningPhase={running} />
    }

    const { container } = render(<Harness />)
    expect(openPhaseLabel(container)).toBe('Data')
    // Click the Verify trigger; without the #311 fix the parent's snap-back
    // would reset to the fallback (`data`).
    const verifyTrigger = Array.from(container.querySelectorAll('button')).find((b) =>
      (b.textContent ?? '').includes('Verify'),
    )
    expect(verifyTrigger).toBeDefined()
    fireEvent.click(verifyTrigger!)
    expect(openPhaseLabel(container)).toBe('Verify')
  })

  it('re-syncs the open panel when runningPhase changes', () => {
    const phases = [
      { id: 'data', label: 'Data', steps: [makeStep('precheck', 'pass')] },
      { id: 'modeling', label: 'Modeling', steps: [makeStep('train', 'idle')] },
    ]
    const { container, rerender } = render(
      <DemoPhasePanel phases={phases} runningPhase="data" />,
    )
    expect(openPhaseLabel(container)).toBe('Data')
    rerender(<DemoPhasePanel phases={phases} runningPhase="modeling" />)
    expect(openPhaseLabel(container)).toBe('Modeling')
  })
})
