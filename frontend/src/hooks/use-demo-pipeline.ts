import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useWebSocket } from '@/hooks/use-websocket'
import { DEMO_WS_URL } from '@/lib/constants'
import type { DemoRunRequest, ScenarioPreset, StepEvent } from '@/types/api'
import { PHASE_LABEL, phaseDefsForScenario } from '@/components/demo/PHASE_DEFS'

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
  /** PRP-38 — populated when the wire event carries `phase_name`. */
  phaseName?: string
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

/**
 * Build the initial idle-card list for one scenario. PRP-38 — DEMO_MINIMAL
 * keeps the legacy 11-card layout; SHOWCASE_RICH renders the full 14-card
 * layout up front so the operator sees the whole flow at idle.
 */
export function createInitialSteps(
  scenario: ScenarioPreset = 'demo_minimal'
): DemoStep[] {
  return phaseDefsForScenario(scenario).map((def) => ({
    name: def.step,
    label: def.label,
    status: 'idle',
    detail: '',
    durationMs: 0,
    data: {},
    phaseName: def.phase,
  }))
}

/** The fresh pipeline state used before a run and on reset. */
export function initialState(
  scenario: ScenarioPreset = 'demo_minimal'
): DemoPipelineState {
  return {
    steps: createInitialSteps(scenario),
    phase: 'idle',
    summary: null,
    errorMessage: null,
  }
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
        step.name === event.step_name
          ? {
              ...step,
              status: 'running' as const,
              // PRP-38 — adopt phase metadata from the wire when present.
              phaseName: event.phase_name ?? step.phaseName,
            }
          : step
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
              phaseName: event.phase_name ?? step.phaseName,
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

export interface PhaseGroup {
  id: string
  label: string
  steps: DemoStep[]
}

/**
 * PRP-38 — group a flat step list by `phaseName` (set when wire events carry
 * `phase_name`). Legacy back-compat: when no step carries a phase, returns
 * a single `pipeline` bucket so the page still renders.
 */
export function derivePhases(steps: DemoStep[]): PhaseGroup[] {
  const hasPhases = steps.some((s) => !!s.phaseName)
  if (!hasPhases) {
    return [{ id: 'pipeline', label: 'Pipeline', steps }]
  }
  const phaseOrder: string[] = []
  const byPhase = new Map<string, DemoStep[]>()
  for (const s of steps) {
    const p = s.phaseName ?? 'pipeline'
    if (!byPhase.has(p)) {
      phaseOrder.push(p)
      byPhase.set(p, [])
    }
    const bucket = byPhase.get(p)
    if (bucket) bucket.push(s)
  }
  return phaseOrder.map((id) => ({
    id,
    label: PHASE_LABEL[id] ?? id,
    steps: byPhase.get(id) ?? [],
  }))
}

export interface UseDemoPipelineResult {
  steps: DemoStep[]
  phases: PhaseGroup[]
  /** Phase id of the most recently `running` step, for accordion auto-expand. */
  runningPhase: string | null
  phase: DemoPhase
  summary: DemoSummary | null
  errorMessage: string | null
  isRunning: boolean
  connectionStatus: ReturnType<typeof useWebSocket>['status']
  start: (req: DemoRunRequest) => void
  /** PRP-38 — caller-supplied scenario; controls the idle layout. */
  setScenario: (scenario: ScenarioPreset) => void
  scenario: ScenarioPreset
}

/**
 * Drive the in-product demo pipeline over a one-shot WebSocket.
 *
 * `start(req)` resets the cards, opens the socket, and sends the start frame
 * once connected. The socket is closed on `pipeline_complete` / `error` so it
 * never auto-reconnects and re-triggers a run.
 *
 * PRP-38 — accepts a scenario so the idle-card layout matches the run that
 * will be triggered (14 cards for SHOWCASE_RICH; 11 for DEMO_MINIMAL).
 */
export function useDemoPipeline(): UseDemoPipelineResult {
  const [scenario, setScenarioInternal] = useState<ScenarioPreset>('demo_minimal')
  const [state, setState] = useState<DemoPipelineState>(() => initialState('demo_minimal'))
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

  // PRP-38 — switching scenarios from idle re-renders the idle-card layout
  // in one state update; this avoids the lint-flagged setState-in-effect
  // anti-pattern.
  const setScenario = useCallback((next: ScenarioPreset) => {
    setScenarioInternal(next)
    setState((prev) => (prev.phase === 'idle' ? initialState(next) : prev))
  }, [])

  const start = useCallback(
    (req: DemoRunRequest) => {
      const nextScenario = req.scenario ?? scenario
      setState({ ...initialState(nextScenario), phase: 'running' })
      pendingReq.current = req
      reconnect()
    },
    [reconnect, scenario]
  )

  const phases = useMemo(() => derivePhases(state.steps), [state.steps])
  const runningStep = state.steps.find((s) => s.status === 'running')
  const runningPhase = runningStep?.phaseName ?? null

  return {
    steps: state.steps,
    phases,
    runningPhase,
    phase: state.phase,
    summary: state.summary,
    errorMessage: state.errorMessage,
    isRunning: state.phase === 'running',
    connectionStatus: status,
    start,
    setScenario,
    scenario,
  }
}
