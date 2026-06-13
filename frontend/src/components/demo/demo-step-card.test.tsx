/**
 * PRP-39 — render tests for the 4 new step kinds' mini-summary chip-lines
 * and the Inspect deep-link hrefs they expose.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { DemoStep } from '@/hooks/use-demo-pipeline'
import { DemoStepCard } from './demo-step-card'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

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

  // ============================================================
  // PRP-41 — HitlFlowSummary, ApproveButton, OpsSnapshotMiniGrid
  // ============================================================

  it('agent_hitl_flow — terminal pass renders HitlFlowSummary with the approval decision', () => {
    const step = makeStep('agent_hitl_flow', 'pass', {
      session_id: 'sess-abcdef0123456',
      tokens_used: 240,
      tool_calls_count: 1,
      action_id: 'act-x',
      approval_decision: 'executed',
    })
    const { container } = renderCard(step, null)
    const text = container.textContent ?? ''
    expect(text).toContain('session=sess-abc')
    expect(text).toContain('tokens=240')
    expect(text).toContain('tool_calls=1')
    expect(text).toContain('approval=executed')
  })

  it('agent_hitl_flow — running + awaiting_approval=true surfaces Approve and Reject', () => {
    const step = makeStep('agent_hitl_flow', 'running', {
      session_id: 'sess-x',
      awaiting_approval: true,
      action_id: 'act-y',
      decision_window_s: 10,
    })
    const { container } = renderCard(step, null)
    const buttons = Array.from(container.querySelectorAll('button')).map((b) => b.textContent)
    expect(buttons).toContain('Approve')
    expect(buttons).toContain('Reject')
  })

  it('agent_hitl_flow — terminal status hides the decision buttons', () => {
    const step = makeStep('agent_hitl_flow', 'pass', {
      session_id: 'sess-x',
      awaiting_approval: true, // stale flag from intermediate event
      action_id: 'act-y',
      decision_window_s: 10,
    })
    const { container } = renderCard(step, null)
    const buttons = Array.from(container.querySelectorAll('button')).map((b) => b.textContent)
    expect(buttons).not.toContain('Approve')
    expect(buttons).not.toContain('Reject')
  })

  it('agent_hitl_flow — countdown reads data.decision_window_s', () => {
    const step = makeStep('agent_hitl_flow', 'running', {
      session_id: 'sess-x',
      awaiting_approval: true,
      action_id: 'act-y',
      decision_window_s: 7,
    })
    const { container } = renderCard(step, null)
    expect(container.textContent).toContain('auto-approve in 7s')
  })

  it('agent_hitl_flow — Approve POSTs the demo relay with the approved decision', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    const step = makeStep('agent_hitl_flow', 'running', {
      session_id: 'sess-x',
      awaiting_approval: true,
      action_id: 'act-y',
      decision_window_s: 10,
    })
    renderCard(step, null)
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const call = fetchMock.mock.calls[0]!
    expect(String(call[0])).toContain('/demo/hitl-decision')
    const init = call[1] as RequestInit
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({ action_id: 'act-y', decision: 'approved' })
    // Both buttons disable after a click.
    expect(screen.getByRole('button', { name: 'Approving…' })).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Reject' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('agent_hitl_flow — Reject POSTs the demo relay with the rejected decision', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    const step = makeStep('agent_hitl_flow', 'running', {
      session_id: 'sess-x',
      awaiting_approval: true,
      action_id: 'act-z',
      decision_window_s: 10,
    })
    renderCard(step, null)
    fireEvent.click(screen.getByRole('button', { name: 'Reject' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const init = fetchMock.mock.calls[0]![1] as RequestInit
    expect(JSON.parse(String(init.body))).toEqual({ action_id: 'act-z', decision: 'rejected' })
    expect(screen.getByRole('button', { name: 'Rejecting…' })).toBeTruthy()
  })

  it('agent_hitl_flow — absorbs a 404 (auto-approve raced) without surfacing an error', async () => {
    const problem = JSON.stringify({ status: 404, detail: 'No pending HITL action' })
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(problem, {
        status: 404,
        headers: { 'content-type': 'application/problem+json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const step = makeStep('agent_hitl_flow', 'running', {
      session_id: 'sess-x',
      awaiting_approval: true,
      action_id: 'act-y',
      decision_window_s: 10,
    })
    const { container } = renderCard(step, null)
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(container.textContent).not.toMatch(/decision failed/)
  })

  it('ops_snapshot — renders the 5-tile mini grid with values', () => {
    const step = makeStep('ops_snapshot', 'pass', {
      stale_aliases_count: 1,
      retraining_candidates_count: 2,
      total_runs: 5,
      total_aliases: 2,
      degrading_health_count: 1,
    })
    const { container } = renderCard(step, null)
    // 5 tiles in a grid-cols-5; each tile has a label + value.
    const tileLabels = Array.from(
      container.querySelectorAll('.grid-cols-5 .text-muted-foreground'),
    ).map((d) => d.textContent)
    expect(tileLabels).toEqual([
      'stale_aliases',
      'retraining',
      'runs',
      'aliases',
      'degrading',
    ])
  })

  it('ops_snapshot — renders em-dash for missing keys', () => {
    const step = makeStep('ops_snapshot', 'pass', {
      stale_aliases_count: 3,
      // others missing
    })
    const { container } = renderCard(step, null)
    const values = Array.from(
      container.querySelectorAll('.grid-cols-5 .font-mono.font-semibold'),
    ).map((d) => d.textContent)
    expect(values[0]).toBe('3')
    expect(values.slice(1)).toEqual(['—', '—', '—', '—'])
  })
})
