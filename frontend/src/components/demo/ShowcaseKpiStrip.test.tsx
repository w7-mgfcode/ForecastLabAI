import { cleanup, render } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { ShowcaseKpiStrip } from './ShowcaseKpiStrip'
import type { DemoStep } from '@/hooks/use-demo-pipeline'

afterEach(() => cleanup())

const makeStep = (overrides: Partial<DemoStep>): DemoStep => ({
  name: 'unset',
  label: 'unset',
  status: 'pass',
  detail: '',
  durationMs: 0,
  data: {},
  phaseName: 'data',
  ...overrides,
})

describe('ShowcaseKpiStrip', () => {
  it('renders nothing until at least one step reaches a terminal status', () => {
    const steps = [makeStep({ name: 'precheck', status: 'idle' })]
    const { container } = render(<ShowcaseKpiStrip steps={steps} />)
    expect(container.firstChild).toBeNull()
  })

  it('counts runs_registered from register / v2_train / stale_alias_trigger / safer_promote_flow', () => {
    const steps = [
      makeStep({ name: 'register', status: 'pass', data: { run_id: 'r1' } }),
      makeStep({ name: 'v2_train', status: 'pass', data: { run_id: 'r2' } }),
      makeStep({ name: 'stale_alias_trigger', status: 'pass', data: { run_id: 'r3' } }),
      makeStep({ name: 'safer_promote_flow', status: 'pass', data: { run_id: 'r4' } }),
      // Not a counter: no run_id.
      makeStep({ name: 'register', status: 'pass', data: {} }),
    ]
    const { container } = render(<ShowcaseKpiStrip steps={steps} />)
    const tile = Array.from(container.querySelectorAll('div.font-mono.text-2xl')).find(
      (d) => (d.previousElementSibling?.textContent ?? '') === 'Runs registered',
    )
    expect(tile?.textContent).toBe('4')
  })

  it('prefers ops_snapshot.total_aliases for the aliases_live tile', () => {
    const steps = [
      makeStep({
        name: 'ops_snapshot',
        status: 'pass',
        data: { total_aliases: 7 },
      }),
    ]
    const { container } = render(<ShowcaseKpiStrip steps={steps} />)
    const tile = Array.from(container.querySelectorAll('div.font-mono.text-2xl')).find(
      (d) => (d.previousElementSibling?.textContent ?? '') === 'Aliases live',
    )
    expect(tile?.textContent).toBe('7')
  })

  it('counts plans_saved across scenario_simulate_and_save + multi_plan_compare', () => {
    const steps = [
      makeStep({
        name: 'scenario_simulate_and_save',
        status: 'pass',
        data: { scenario_id: 'scn-1' },
      }),
      makeStep({
        name: 'multi_plan_compare',
        status: 'pass',
        data: { winner_scenario_id: 'scn-2', ranked: [{ name: 'a' }, { name: 'b' }] },
      }),
    ]
    const { container } = render(<ShowcaseKpiStrip steps={steps} />)
    const tile = Array.from(container.querySelectorAll('div.font-mono.text-2xl')).find(
      (d) => (d.previousElementSibling?.textContent ?? '') === 'Plans saved',
    )
    expect(tile?.textContent).toBe('2')
  })

  it('renders em-dash for missing data', () => {
    const steps = [makeStep({ name: 'register', status: 'pass', data: {} })]
    const { container } = render(<ShowcaseKpiStrip steps={steps} />)
    // Batch items + RAG chunks have no source; rendered as em-dash.
    const tiles = Array.from(container.querySelectorAll('div.font-mono.text-2xl'))
    const batch = tiles.find(
      (d) => (d.previousElementSibling?.textContent ?? '') === 'Batch items',
    )
    expect(batch?.textContent).toBe('—')
  })
})
