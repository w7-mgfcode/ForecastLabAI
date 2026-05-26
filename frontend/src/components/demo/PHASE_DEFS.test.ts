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

  it('showcase_rich -> the 14-step sequence with phase2_enrichment/historical_backfill/v2_train', () => {
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

  it('PHASE_ORDER contains exactly the six canonical phases', () => {
    expect(PHASE_ORDER).toEqual(['data', 'modeling', 'decision', 'verify', 'agent', 'cleanup'])
  })

  it('PHASE_LABEL has a label per canonical phase', () => {
    for (const phase of PHASE_ORDER) {
      const label = PHASE_LABEL[phase]
      expect(label).toBeDefined()
      expect((label ?? '').length).toBeGreaterThan(0)
    }
  })
})
