import { useCallback, useEffect, useRef, useState } from 'react'
import { useWebSocket } from '@/hooks/use-websocket'
import { DEMO_WS_URL } from '@/lib/constants'
import type { DemoRunRequest, StepEvent } from '@/types/api'

// UI-side step status -- adds 'idle' to the wire-level DemoStepStatus.
export type DemoStepUiStatus = 'idle' | 'running' | 'pass' | 'fail' | 'skip' | 'warn'

// Overall pipeline phase.
export type DemoPhase = 'idle' | 'running' | 'done' | 'error'

export interface DemoStep {
  name: string
  label: string
  status: DemoStepUiStatus
  detail: string
  durationMs: number
  data: Record<string, unknown>
}

export interface DemoSummary {
  overallStatus: 'pass' | 'fail'
  winnerModelType: string | null
  winnerWape: number | null
  winningRunId: string | null
  alias: string | null
  wallClockS: number
}

export interface DemoPipelineState {
  steps: DemoStep[]
  phase: DemoPhase
  summary: DemoSummary | null
  errorMessage: string | null
}

// The 11 pipeline steps, in order. Mirrors the backend `_step_table()` in
// app/features/demo/pipeline.py so the page can render idle cards before a run.
const STEP_DEFS: ReadonlyArray<{ name: string; label: string }> = [
  { name: 'precheck', label: 'Health check' },
  { name: 'reset', label: 'Reset database' },
  { name: 'seed', label: 'Seed demo data' },
  { name: 'status', label: 'Inspect dataset' },
  { name: 'features', label: 'Compute features' },
  { name: 'train', label: 'Train models' },
  { name: 'backtest', label: 'Backtest models' },
  { name: 'register', label: 'Register winner' },
  { name: 'verify', label: 'Verify artifact' },
  { name: 'agent', label: 'Agent chat' },
  { name: 'cleanup', label: 'Cleanup' },
]

/** Build the 11 step cards in their initial idle state. */
export function createInitialSteps(): DemoStep[] {
  return STEP_DEFS.map((def) => ({
    name: def.name,
    label: def.label,
    status: 'idle',
    detail: '',
    durationMs: 0,
    data: {},
  }))
}

/** The fresh pipeline state used before a run and on reset. */
export function initialState(): DemoPipelineState {
  return { steps: createInitialSteps(), phase: 'idle', summary: null, errorMessage: null }
}

function toNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function toStringOrNull(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

/**
 * Pure reducer: fold one streamed StepEvent into the pipeline state.
 *
 * Exported so the state machine is unit-testable without a WebSocket.
 */
export function applyEvent(state: DemoPipelineState, event: StepEvent): DemoPipelineState {
  switch (event.event_type) {
    case 'step_start': {
      const steps = state.steps.map((step) =>
        step.name === event.step_name ? { ...step, status: 'running' as const } : step
      )
      return { ...state, steps, phase: 'running' }
    }
    case 'step_complete': {
      const status: DemoStepUiStatus = event.status ?? 'pass'
      const steps = state.steps.map((step) =>
        step.name === event.step_name
          ? {
              ...step,
              status,
              detail: event.detail,
              durationMs: event.duration_ms,
              data: event.data,
            }
          : step
      )
      return { ...state, steps }
    }
    case 'pipeline_complete': {
      const summary: DemoSummary = {
        overallStatus: event.status === 'fail' ? 'fail' : 'pass',
        winnerModelType: toStringOrNull(event.data.winner_model_type),
        winnerWape: toNumber(event.data.winner_wape),
        winningRunId: toStringOrNull(event.data.winning_run_id),
        alias: toStringOrNull(event.data.alias),
        wallClockS: toNumber(event.data.wall_clock_s) ?? 0,
      }
      return { ...state, phase: 'done', summary }
    }
    case 'error': {
      return { ...state, phase: 'error', errorMessage: event.detail || 'Pipeline error' }
    }
    default:
      return state
  }
}

export interface UseDemoPipelineResult {
  steps: DemoStep[]
  phase: DemoPhase
  summary: DemoSummary | null
  errorMessage: string | null
  isRunning: boolean
  connectionStatus: ReturnType<typeof useWebSocket>['status']
  start: (req: DemoRunRequest) => void
}

/**
 * Drive the in-product demo pipeline over a one-shot WebSocket.
 *
 * `start(req)` resets the cards, opens the socket, and sends the start frame
 * once connected. The socket is closed on `pipeline_complete` / `error` so it
 * never auto-reconnects and re-triggers a run.
 */
export function useDemoPipeline(): UseDemoPipelineResult {
  const [state, setState] = useState<DemoPipelineState>(initialState)
  const pendingReq = useRef<DemoRunRequest | null>(null)
  const disconnectRef = useRef<(() => void) | null>(null)

  const handleMessage = useCallback((data: unknown) => {
    const event = data as StepEvent
    setState((prev) => applyEvent(prev, event))
    if (event.event_type === 'pipeline_complete' || event.event_type === 'error') {
      disconnectRef.current?.()
    }
  }, [])

  const { status, send, disconnect, reconnect } = useWebSocket(DEMO_WS_URL, {
    onMessage: handleMessage,
    autoConnect: false,
  })

  useEffect(() => {
    disconnectRef.current = disconnect
  }, [disconnect])

  // Send the queued start frame once the socket is open.
  useEffect(() => {
    if (status === 'connected' && pendingReq.current) {
      send(pendingReq.current)
      pendingReq.current = null
    }
  }, [status, send])

  const start = useCallback(
    (req: DemoRunRequest) => {
      setState({ ...initialState(), phase: 'running' })
      pendingReq.current = req
      reconnect()
    },
    [reconnect]
  )

  return {
    steps: state.steps,
    phase: state.phase,
    summary: state.summary,
    errorMessage: state.errorMessage,
    isRunning: state.phase === 'running',
    connectionStatus: status,
    start,
  }
}
