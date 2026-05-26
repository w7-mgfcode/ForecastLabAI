/**
 * PRP-38 — lockstep test for the (phase, step) contract between
 * `app/features/demo/pipeline.py:_phase_table()` and this file.
 *
 * The backend test `app/features/demo/tests/test_pipeline.py::test_phase_table_*`
 * pins the same tuple list; if either tier drifts the matching test fails.
 */

import { describe, expect, it } from 'vitest'
import { PHASE_LABEL, PHASE_ORDER, phaseDefsForScenario } from './PHASE_DEFS'

describe('PHASE_DEFS lockstep with backend _phase_table', () => {
  it('demo_minimal -> the legacy 11-step (phase, step) sequence', () => {
    const tuples = phaseDefsForScenario('demo_minimal').map((d) => [d.phase, d.step])
    expect(tuples).toEqual([
      ['data', 'precheck'],
      ['data', 'reset'],
      ['data', 'seed'],
      ['data', 'status'],
      ['data', 'features'],
      ['modeling', 'train'],
      ['decision', 'backtest'],
      ['decision', 'register'],
      ['verify', 'verify'],
      ['agent', 'agent'],
      ['cleanup', 'cleanup'],
    ])
  })

  it('showcase_rich -> the 18-step sequence with PRP-38 V2 + PRP-39 decision/portfolio rows', () => {
    const tuples = phaseDefsForScenario('showcase_rich').map((d) => [d.phase, d.step])
    expect(tuples).toEqual([
      ['data', 'precheck'],
      ['data', 'reset'],
      ['data', 'seed'],
      ['data', 'status'],
      ['data', 'features'],
      ['data', 'phase2_enrichment'],
      ['data', 'historical_backfill'],
      ['modeling', 'train'],
      ['modeling', 'v2_train'],
      ['decision', 'backtest'],
      ['decision', 'register'],
      // PRP-39 — three decision-phase extensions after register.
      ['decision', 'champion_compat_compare'],
      ['decision', 'stale_alias_trigger'],
      ['decision', 'safer_promote_flow'],
      // PRP-39 — new portfolio phase between decision and verify.
      ['portfolio', 'batch_preset'],
      ['verify', 'verify'],
      ['agent', 'agent'],
      ['cleanup', 'cleanup'],
    ])
  })

  it('sparse -> matches the demo_minimal shape (picker option only)', () => {
    const sparse = phaseDefsForScenario('sparse')
    const minimal = phaseDefsForScenario('demo_minimal')
    expect(sparse).toEqual(minimal)
  })

  it('PHASE_ORDER contains exactly the seven canonical phases (PRP-39 adds portfolio)', () => {
    expect(PHASE_ORDER).toEqual([
      'data',
      'modeling',
      'decision',
      'portfolio',
      'verify',
      'agent',
      'cleanup',
    ])
  })

  it('PHASE_LABEL has a label per canonical phase', () => {
    for (const phase of PHASE_ORDER) {
      const label = PHASE_LABEL[phase]
      expect(label).toBeDefined()
      expect((label ?? '').length).toBeGreaterThan(0)
    }
  })
})
