import { describe, it, expect } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import {
  applyEvent,
  createInitialSteps,
  derivePhases,
  initialState,
  useDemoPipeline,
} from './use-demo-pipeline'
import type { DemoStep } from './use-demo-pipeline'
import type { StepEvent } from '@/types/api'

/** Build a StepEvent with sensible defaults for the fields not under test. */
function makeEvent(partial: Partial<StepEvent> & Pick<StepEvent, 'event_type'>): StepEvent {
  return {
    event_type: partial.event_type,
    step_name: partial.step_name ?? 'precheck',
    step_index: partial.step_index ?? 1,
    total_steps: partial.total_steps ?? 11,
    status: partial.status ?? null,
    detail: partial.detail ?? '',
    duration_ms: partial.duration_ms ?? 0,
    data: partial.data ?? {},
    timestamp: partial.timestamp ?? '2026-05-17T00:00:00Z',
  }
}

describe('createInitialSteps', () => {
  it('creates 11 idle steps in pipeline order', () => {
    const steps = createInitialSteps()
    expect(steps).toHaveLength(11)
    expect(steps.every((s) => s.status === 'idle')).toBe(true)
    expect(steps[0]?.name).toBe('precheck')
    expect(steps[10]?.name).toBe('cleanup')
  })
})

describe('initialState', () => {
  it('starts idle with no summary and no error', () => {
    const state = initialState()
    expect(state.phase).toBe('idle')
    expect(state.summary).toBeNull()
    expect(state.errorMessage).toBeNull()
  })
})

describe('applyEvent', () => {
  it('marks a step running on step_start and enters the running phase', () => {
    const next = applyEvent(
      initialState(),
      makeEvent({ event_type: 'step_start', step_name: 'train' })
    )
    expect(next.phase).toBe('running')
    expect(next.steps.find((s) => s.name === 'train')?.status).toBe('running')
    expect(next.steps.find((s) => s.name === 'precheck')?.status).toBe('idle')
  })

  it('records the outcome on step_complete', () => {
    const next = applyEvent(
      initialState(),
      makeEvent({
        event_type: 'step_complete',
        step_name: 'backtest',
        status: 'pass',
        detail: '3 models',
        duration_ms: 1500,
        data: { winner: 'naive' },
      })
    )
    const step = next.steps.find((s) => s.name === 'backtest')
    expect(step?.status).toBe('pass')
    expect(step?.detail).toBe('3 models')
    expect(step?.durationMs).toBe(1500)
    expect(step?.data).toEqual({ winner: 'naive' })
  })

  it('defaults a null step_complete status to pass', () => {
    const next = applyEvent(
      initialState(),
      makeEvent({ event_type: 'step_complete', step_name: 'seed', status: null })
    )
    expect(next.steps.find((s) => s.name === 'seed')?.status).toBe('pass')
  })

  it('builds a summary on pipeline_complete', () => {
    const next = applyEvent(
      initialState(),
      makeEvent({
        event_type: 'pipeline_complete',
        step_name: 'summary',
        status: 'pass',
        data: {
          winner_model_type: 'seasonal_naive',
          winner_wape: 0.12,
          winning_run_id: 'run-abc',
          alias: 'demo-production',
          wall_clock_s: 42,
        },
      })
    )
    expect(next.phase).toBe('done')
    expect(next.summary).toEqual({
      overallStatus: 'pass',
      winnerModelType: 'seasonal_naive',
      winnerWape: 0.12,
      winningRunId: 'run-abc',
      alias: 'demo-production',
      wallClockS: 42,
      v2RunId: null,
      workspaceId: null,
    })
  })

  it('E4 (#393) — captures workspace_id from pipeline_complete data', () => {
    const next = applyEvent(
      initialState(),
      makeEvent({
        event_type: 'pipeline_complete',
        step_name: 'summary',
        status: 'pass',
        data: { workspace_id: 'ws-e4-abc' },
      })
    )
    expect(next.summary?.workspaceId).toBe('ws-e4-abc')
  })

  it('E4 (#393) — legacy pipeline_complete without workspace_id yields null', () => {
    const next = applyEvent(
      initialState(),
      makeEvent({ event_type: 'pipeline_complete', step_name: 'summary', status: 'pass', data: {} })
    )
    expect(next.summary?.workspaceId).toBeNull()
  })

  it('reports a failed pipeline_complete as fail', () => {
    const next = applyEvent(
      initialState(),
      makeEvent({ event_type: 'pipeline_complete', step_name: 'summary', status: 'fail', data: {} })
    )
    expect(next.phase).toBe('done')
    expect(next.summary?.overallStatus).toBe('fail')
    expect(next.summary?.winnerModelType).toBeNull()
  })

  it('sets the error phase on an error event', () => {
    const next = applyEvent(
      initialState(),
      makeEvent({ event_type: 'error', detail: 'already running' })
    )
    expect(next.phase).toBe('error')
    expect(next.errorMessage).toBe('already running')
  })

  it('transitions a step idle -> running -> pass across events', () => {
    let state = initialState()
    expect(state.steps.find((s) => s.name === 'features')?.status).toBe('idle')

    state = applyEvent(state, makeEvent({ event_type: 'step_start', step_name: 'features' }))
    expect(state.steps.find((s) => s.name === 'features')?.status).toBe('running')

    state = applyEvent(
      state,
      makeEvent({ event_type: 'step_complete', step_name: 'features', status: 'pass' })
    )
    expect(state.steps.find((s) => s.name === 'features')?.status).toBe('pass')
  })

  it('reaches the done phase after a full step + summary sequence', () => {
    let state = initialState()
    state = applyEvent(state, makeEvent({ event_type: 'step_start', step_name: 'precheck' }))
    state = applyEvent(
      state,
      makeEvent({ event_type: 'step_complete', step_name: 'precheck', status: 'pass' })
    )
    expect(state.phase).toBe('running')

    state = applyEvent(
      state,
      makeEvent({
        event_type: 'pipeline_complete',
        step_name: 'summary',
        status: 'pass',
        data: {},
      })
    )
    expect(state.phase).toBe('done')
  })
})

describe('useDemoPipeline', () => {
  it('initializes with 11 idle steps and the idle phase (demo_minimal default)', () => {
    const { result } = renderHook(() => useDemoPipeline())
    expect(result.current.steps).toHaveLength(11)
    expect(result.current.phase).toBe('idle')
    expect(result.current.isRunning).toBe(false)
    expect(result.current.summary).toBeNull()
    // PRP-38 — every idle step carries a phase tag (no real wire events yet).
    expect(result.current.steps.every((s) => !!s.phaseName)).toBe(true)
    expect(result.current.phases.length).toBe(6)
    // PRP-41 — design Z renamed the legacy `agent` phase to the unified `agents`.
    expect(result.current.phases.map((p) => p.id)).toEqual([
      'data',
      'modeling',
      'decision',
      'verify',
      'agents',
      'cleanup',
    ])
  })

  it('PRP-41 — stop() resets phase to idle and surfaces a cancellation banner', () => {
    const { result, rerender } = renderHook(() => useDemoPipeline())
    // Drive into running state via start().
    act(() => {
      result.current.start({ seed: 42, skip_seed: true, reset: false, scenario: 'demo_minimal' })
    })
    expect(result.current.phase).toBe('running')
    act(() => {
      result.current.stop()
    })
    rerender()
    expect(result.current.phase).toBe('idle')
    expect(result.current.errorMessage).toBe('Pipeline cancelled by user.')
  })
})


// =============================================================================
// PRP-38 — derivePhases + phase-aware applyEvent + showcase_rich layout
// =============================================================================


describe('PRP-38 derivePhases', () => {
  it('groups steps by phaseName preserving first-seen order', () => {
    const steps: DemoStep[] = [
      {
        name: 'precheck',
        label: 'Health check',
        status: 'pass',
        detail: '',
        durationMs: 0,
        data: {},
        phaseName: 'data',
      },
      {
        name: 'train',
        label: 'Train models',
        status: 'pass',
        detail: '',
        durationMs: 0,
        data: {},
        phaseName: 'modeling',
      },
      {
        name: 'reset',
        label: 'Reset',
        status: 'skip',
        detail: '',
        durationMs: 0,
        data: {},
        phaseName: 'data',
      },
    ]
    const groups = derivePhases(steps)
    expect(groups.map((g) => g.id)).toEqual(['data', 'modeling'])
    expect(groups[0]?.steps.map((s) => s.name)).toEqual(['precheck', 'reset'])
    expect(groups[1]?.steps.map((s) => s.name)).toEqual(['train'])
  })

  it("falls back to a 'pipeline' bucket when no step carries a phase (legacy)", () => {
    const steps: DemoStep[] = [
      {
        name: 'precheck',
        label: 'Health check',
        status: 'pass',
        detail: '',
        durationMs: 0,
        data: {},
      },
    ]
    const groups = derivePhases(steps)
    expect(groups.length).toBe(1)
    expect(groups[0]?.id).toBe('pipeline')
  })
})


describe('PRP-38 applyEvent phase propagation', () => {
  it('captures phase_name from a step_start event', () => {
    const next = applyEvent(
      initialState(),
      makeEvent({ event_type: 'step_start', step_name: 'train', phase_name: 'modeling' })
    )
    const step = next.steps.find((s) => s.name === 'train')
    expect(step?.phaseName).toBe('modeling')
  })

  it('captures phase_name from a step_complete event', () => {
    const next = applyEvent(
      initialState(),
      makeEvent({
        event_type: 'step_complete',
        step_name: 'backtest',
        status: 'pass',
        phase_name: 'decision',
      })
    )
    expect(next.steps.find((s) => s.name === 'backtest')?.phaseName).toBe('decision')
  })
})


describe('PRP-38/39/40/41 createInitialSteps(showcase_rich)', () => {
  it('returns 24 idle steps in the showcase_rich layout (PRP-41 adds agent_hitl_flow + ops_snapshot)', () => {
    const steps = createInitialSteps('showcase_rich')
    expect(steps.length).toBe(24)
    expect(steps.map((s) => s.name)).toEqual([
      'precheck',
      'reset',
      'seed',
      'status',
      'features',
      'phase2_enrichment',
      'historical_backfill',
      'train',
      'v2_train',
      'backtest',
      'register',
      // PRP-39 — decision-phase extensions.
      'champion_compat_compare',
      'stale_alias_trigger',
      'safer_promote_flow',
      // PRP-39 — portfolio phase (between decision and verify).
      'batch_preset',
      // PRP-40 — planning + knowledge phases (after portfolio, before verify).
      'scenario_simulate_and_save',
      'multi_plan_compare',
      'embedding_provider_probe',
      'rag_index_subset',
      'rag_retrieve_probe',
      'verify',
      // PRP-41 — HITL approval + ops snapshot (replaces legacy `agent`).
      'agent_hitl_flow',
      'ops_snapshot',
      'cleanup',
    ])
  })
})
