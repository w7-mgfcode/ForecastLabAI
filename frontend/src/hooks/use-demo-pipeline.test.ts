import { describe, it, expect } from 'vitest'
import { renderHook } from '@testing-library/react'
import {
  applyEvent,
  createInitialSteps,
  initialState,
  useDemoPipeline,
} from './use-demo-pipeline'
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
    })
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
  it('initializes with 11 idle steps and the idle phase', () => {
    const { result } = renderHook(() => useDemoPipeline())
    expect(result.current.steps).toHaveLength(11)
    expect(result.current.phase).toBe('idle')
    expect(result.current.isRunning).toBe(false)
    expect(result.current.summary).toBeNull()
  })
})
