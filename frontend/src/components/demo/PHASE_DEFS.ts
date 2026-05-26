/**
 * PRP-38 — Single source of truth for the demo pipeline's phase grouping.
 *
 * Mirrors `app/features/demo/pipeline.py:_phase_table()` lock-step. The paired
 * tests `app/features/demo/tests/test_pipeline.py::test_phase_table_*` and
 * the frontend `PHASE_DEFS.test.ts` together gate this contract — drift in
 * either tier breaks the matching test.
 */

import type { ScenarioPreset } from '@/types/api'

export interface PhaseDef {
  /** Phase id — matches the backend `phase_name` field on a StepEvent. */
  phase: string
  /** Step id — matches the backend `step_name` field on a StepEvent. */
  step: string
  /** Human-readable label rendered on the step card. */
  label: string
}

/**
 * The complete set of step definitions used by either DEMO_MINIMAL (legacy
 * 11 steps) or SHOWCASE_RICH (11 + 3 = 14 steps).
 *
 * Order matters: each row's (phase, step) tuple list is what the lockstep
 * test asserts equals the backend's `_phase_table(scenario)` output for
 * the matching scenario.
 */
const ALL_STEPS: ReadonlyArray<PhaseDef> = [
  { phase: 'data', step: 'precheck', label: 'Health check' },
  { phase: 'data', step: 'reset', label: 'Reset database' },
  { phase: 'data', step: 'seed', label: 'Seed demo data' },
  { phase: 'data', step: 'status', label: 'Inspect dataset' },
  { phase: 'data', step: 'features', label: 'Compute features' },
  { phase: 'data', step: 'phase2_enrichment', label: 'Phase-2 enrichment' },
  { phase: 'data', step: 'historical_backfill', label: 'Historical backfill' },
  { phase: 'modeling', step: 'train', label: 'Train models' },
  { phase: 'modeling', step: 'v2_train', label: 'Train feature-aware (V2)' },
  { phase: 'decision', step: 'backtest', label: 'Backtest models' },
  { phase: 'decision', step: 'register', label: 'Register winner' },
  { phase: 'verify', step: 'verify', label: 'Verify artifact' },
  { phase: 'agent', step: 'agent', label: 'Agent chat' },
  { phase: 'cleanup', step: 'cleanup', label: 'Cleanup' },
] as const

const SHOWCASE_RICH_STEP_NAMES = new Set([
  'phase2_enrichment',
  'historical_backfill',
  'v2_train',
])

/** Return the PhaseDef list for one scenario (lockstep with backend). */
export function phaseDefsForScenario(scenario: ScenarioPreset): readonly PhaseDef[] {
  if (scenario === 'showcase_rich') {
    return ALL_STEPS
  }
  // demo_minimal / sparse / others — legacy 11-step flow (no V2 enrichment).
  return ALL_STEPS.filter((d) => !SHOWCASE_RICH_STEP_NAMES.has(d.step))
}

/** Human-readable label per phase id. */
export const PHASE_LABEL: Record<string, string> = {
  data: 'Data',
  modeling: 'Modeling',
  decision: 'Decision',
  verify: 'Verify',
  agent: 'Agent',
  cleanup: 'Cleanup',
}

/** Canonical phase order — kept in sync with backend constants. */
export const PHASE_ORDER: readonly string[] = [
  'data',
  'modeling',
  'decision',
  'verify',
  'agent',
  'cleanup',
]
