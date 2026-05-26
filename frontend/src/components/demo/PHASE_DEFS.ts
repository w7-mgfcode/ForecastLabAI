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
 * 11 steps) or SHOWCASE_RICH (11 + 3 PRP-38 + 4 PRP-39 + 5 PRP-40 = 23 steps).
 *
 * PRP-39 adds four steps (champion_compat_compare, stale_alias_trigger,
 * safer_promote_flow under the existing decision phase, plus batch_preset
 * under a new portfolio phase between decision and verify).
 *
 * PRP-40 adds five steps grouped under two new phases ("planning" and
 * "knowledge"), inserted after portfolio and BEFORE verify via relative
 * anchors.
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
  // PRP-39 — decision-phase extensions.
  { phase: 'decision', step: 'champion_compat_compare', label: 'Compare V1 vs V2' },
  { phase: 'decision', step: 'stale_alias_trigger', label: 'Trigger stale-alias V mismatch' },
  { phase: 'decision', step: 'safer_promote_flow', label: 'Safer Promote walkthrough' },
  // PRP-39 — new portfolio phase, between decision and verify.
  { phase: 'portfolio', step: 'batch_preset', label: 'Portfolio batch (quick baseline sweep)' },
  // PRP-40 — planning + knowledge phases, after portfolio, before verify.
  { phase: 'planning', step: 'scenario_simulate_and_save', label: 'Simulate & save plan' },
  { phase: 'planning', step: 'multi_plan_compare', label: 'Compare plans' },
  { phase: 'knowledge', step: 'embedding_provider_probe', label: 'Probe embedding provider' },
  { phase: 'knowledge', step: 'rag_index_subset', label: 'Index user-guide corpus' },
  { phase: 'knowledge', step: 'rag_retrieve_probe', label: 'Semantic-retrieve probe' },
  { phase: 'verify', step: 'verify', label: 'Verify artifact' },
  { phase: 'agent', step: 'agent', label: 'Agent chat' },
  { phase: 'cleanup', step: 'cleanup', label: 'Cleanup' },
] as const

const SHOWCASE_RICH_STEP_NAMES = new Set([
  // PRP-38
  'phase2_enrichment',
  'historical_backfill',
  'v2_train',
  // PRP-39 — only render these step rows under scenario=showcase_rich.
  'champion_compat_compare',
  'stale_alias_trigger',
  'safer_promote_flow',
  'batch_preset',
  // PRP-40
  'scenario_simulate_and_save',
  'multi_plan_compare',
  'embedding_provider_probe',
  'rag_index_subset',
  'rag_retrieve_probe',
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
  // PRP-39 — new portfolio phase between decision and verify.
  portfolio: 'Portfolio',
  // PRP-40 — planning + knowledge phases (showcase_rich only).
  planning: 'Planning',
  knowledge: 'Knowledge',
  verify: 'Verify',
  agent: 'Agent',
  cleanup: 'Cleanup',
}

/** Canonical phase order — kept in sync with backend constants. */
export const PHASE_ORDER: readonly string[] = [
  'data',
  'modeling',
  'decision',
  // PRP-39 — portfolio phase between decision and verify.
  'portfolio',
  // PRP-40 — planning + knowledge inserted after portfolio, before verify.
  'planning',
  'knowledge',
  'verify',
  'agent',
  'cleanup',
]
