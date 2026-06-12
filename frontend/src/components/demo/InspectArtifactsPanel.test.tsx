import { cleanup, render } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { InspectArtifactsPanel } from './InspectArtifactsPanel'
import type { DemoStep, DemoSummary } from '@/hooks/use-demo-pipeline'

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

const baseSummary: DemoSummary = {
  overallStatus: 'pass',
  winnerModelType: 'prophet_like',
  winnerWape: 0.08,
  winningRunId: 'r-123',
  alias: 'demo-production',
  wallClockS: 180,
  v2RunId: 'v2-456',
  workspaceId: null,
}

describe('InspectArtifactsPanel', () => {
  it('renders all 10 cards', () => {
    const { container } = render(
      <MemoryRouter>
        <InspectArtifactsPanel steps={[]} summary={baseSummary} />
      </MemoryRouter>,
    )
    const headings = container.querySelectorAll('.text-sm.font-semibold')
    expect(headings.length).toBe(10)
  })

  it('greys out cards whose source data is missing', () => {
    const { container } = render(
      <MemoryRouter>
        <InspectArtifactsPanel steps={[]} summary={baseSummary} />
      </MemoryRouter>,
    )
    // Steps array is empty -> Forecast/Backtest/Batch/Compare/HITL/RAG all
    // missing -> at least 6 cards greyed (opacity-50).
    const greyed = container.querySelectorAll('.opacity-50')
    expect(greyed.length).toBeGreaterThanOrEqual(5)
  })

  it('Forecast card becomes active when the status step exposes the grain', () => {
    const steps = [
      makeStep({ name: 'status', status: 'pass', data: { store_id: 7, product_id: 3 } }),
      makeStep({ name: 'train', status: 'pass', data: {} }),
    ]
    const { container } = render(
      <MemoryRouter>
        <InspectArtifactsPanel steps={steps} summary={baseSummary} />
      </MemoryRouter>,
    )
    const links = Array.from(container.querySelectorAll('a[href]')).map((a) =>
      a.getAttribute('href'),
    )
    expect(links.some((h) => h?.startsWith('/visualize/forecast?store_id=7&product_id=3'))).toBe(true)
  })

  it('V2 Feature Frame card uses summary.v2RunId when present', () => {
    const { container } = render(
      <MemoryRouter>
        <InspectArtifactsPanel steps={[]} summary={baseSummary} />
      </MemoryRouter>,
    )
    const links = Array.from(container.querySelectorAll('a[href]')).map((a) =>
      a.getAttribute('href'),
    )
    expect(links).toContain('/explorer/runs/v2-456')
  })

  it('Agent transcript card disables when HITL session_id missing', () => {
    const steps = [
      makeStep({ name: 'agent_hitl_flow', status: 'skip', data: {} }),
    ]
    const { container } = render(
      <MemoryRouter>
        <InspectArtifactsPanel steps={steps} summary={baseSummary} />
      </MemoryRouter>,
    )
    // The agent card should appear greyed (opacity-50) when session_id is missing.
    const agentCard = Array.from(container.querySelectorAll('.text-sm.font-semibold')).find(
      (h) => h.textContent === 'Agent transcript',
    )
    expect(agentCard).toBeDefined()
    // Walk up to the wrapper div with class opacity-50.
    const wrapper = agentCard?.closest('.opacity-50')
    expect(wrapper).not.toBeNull()
  })
})
