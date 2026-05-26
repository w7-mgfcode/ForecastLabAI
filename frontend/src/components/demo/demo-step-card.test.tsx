/**
 * PRP-39 — render tests for the 4 new step kinds' mini-summary chip-lines
 * and the Inspect deep-link hrefs they expose.
 */

import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { DemoStep } from '@/hooks/use-demo-pipeline'
import { DemoStepCard } from './demo-step-card'

afterEach(cleanup)

function makeStep(
  name: string,
  status: DemoStep['status'],
  data: Record<string, unknown>,
  detail = ''
): DemoStep {
  return {
    name,
    label: name,
    status,
    detail,
    durationMs: 0,
    data,
    phaseName: 'decision',
  }
}

function renderCard(step: DemoStep, inspectHref: string | null = null) {
  return render(
    <MemoryRouter>
      <DemoStepCard step={step} index={0} inspectHref={inspectHref} />
    </MemoryRouter>
  )
}

describe('DemoStepCard PRP-39 mini-summaries', () => {
  it('champion_compat_compare — renders V_a / V_b / compatible chips with reason', () => {
    const step = makeStep('champion_compat_compare', 'pass', {
      v1_run_id: 'v1-aaaa',
      v2_run_id: 'v2-bbbb',
      feature_frame_version_a: null,
      feature_frame_version_b: 2,
      compatible: false,
      comparable_reason: 'feature_frame_version_mismatch',
    })
    renderCard(step)
    expect(screen.getByText(/V_a=1/).textContent).toBeTruthy()
    expect(screen.getByText(/V_b=2/).textContent).toBeTruthy()
    expect(screen.getByText(/compatible=false/).textContent).toBeTruthy()
    expect(screen.getByText(/feature_frame_version_mismatch/).textContent).toBeTruthy()
  })

  it('stale_alias_trigger — renders alias name + stale reason + V mismatch chips', () => {
    const step = makeStep('stale_alias_trigger', 'pass', {
      alias_name: 'demo-production',
      stale_reason: 'feature_frame_version_mismatch',
      alias_feature_frame_version: 2,
      comparable_run_feature_frame_version: 3,
      second_v2_run_id: 'second-v2-cccc',
    })
    renderCard(step)
    expect(screen.getByText(/alias=demo-production/).textContent).toBeTruthy()
    expect(screen.getByText(/stale_reason=feature_frame_version_mismatch/).textContent).toBeTruthy()
    expect(screen.getByText(/V_alias=2/).textContent).toBeTruthy()
    expect(screen.getByText(/V_comparable=3/).textContent).toBeTruthy()
  })

  it('safer_promote_flow — renders alias + before/after short run-id chips', () => {
    const step = makeStep('safer_promote_flow', 'pass', {
      alias_name: 'demo-production',
      before_run_id: 'beforeruna-cafebabe',
      after_run_id: 'afterrunb-deadbeef',
      swap_intent: 'demo_safer_promote_walkthrough',
    })
    renderCard(step)
    expect(screen.getByText(/alias=demo-production/).textContent).toBeTruthy()
    expect(screen.getByText(/before=beforeru/).textContent).toBeTruthy()
    expect(screen.getByText(/after=afterrun/).textContent).toBeTruthy()
  })

  it('batch_preset — renders preset, items, and status chips', () => {
    const step = makeStep('batch_preset', 'pass', {
      batch_id: 'batch-aaaa',
      kind: 'manual',
      preset_source: 'quick_baseline_sweep',
      model_types: ['naive', 'seasonal_naive', 'moving_average'],
      status: 'completed',
      total_items: 18,
      completed_items: 18,
      failed_items: 0,
    })
    renderCard(step)
    expect(screen.getByText(/preset=quick_baseline_sweep/).textContent).toBeTruthy()
    expect(screen.getByText(/18\/18 done/).textContent).toBeTruthy()
    expect(screen.getByText(/status=completed/).textContent).toBeTruthy()
  })

  it('shows the Inspect button on terminal pass with a deep-link href', () => {
    const step = makeStep('batch_preset', 'pass', {
      batch_id: 'batch-aaaa',
      kind: 'manual',
      preset_source: 'quick_baseline_sweep',
      status: 'completed',
      total_items: 18,
      completed_items: 18,
    })
    renderCard(step, '/visualize/batch/batch-aaaa')
    const link = screen.getByRole('link', { name: /Inspect/i }) as HTMLAnchorElement
    expect(link.getAttribute('href')).toBe('/visualize/batch/batch-aaaa')
  })

  it('suppresses the Inspect button when inspectHref is null', () => {
    const step = makeStep('champion_compat_compare', 'pass', {
      compatible: false,
      feature_frame_version_a: null,
      feature_frame_version_b: 2,
      comparable_reason: 'feature_frame_version_mismatch',
    })
    renderCard(step, null)
    const links = screen.queryAllByRole('link', { name: /Inspect/i })
    expect(links.length).toBe(0)
  })
})
