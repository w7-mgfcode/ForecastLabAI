import { cleanup, fireEvent, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { RunHistoryStrip } from './RunHistoryStrip'
import type { DemoSummary } from '@/hooks/use-demo-pipeline'

const STORAGE_KEY = 'forecastlab.showcase.runs.v1'

afterEach(() => {
  cleanup()
  window.localStorage.clear()
})

beforeEach(() => {
  window.localStorage.clear()
})

const summary: DemoSummary = {
  overallStatus: 'pass',
  winnerModelType: 'prophet_like',
  winnerWape: 0.08,
  winningRunId: 'run-abc',
  alias: 'demo-production',
  wallClockS: 174.5,
  v2RunId: 'v2-456',
}

describe('RunHistoryStrip', () => {
  it('renders nothing when no history + no summary yet', () => {
    const { container } = render(
      <RunHistoryStrip onReplay={() => {}} summary={null} scenario="demo_minimal" />,
    )
    expect(container.firstChild).toBeNull()
  })

  it('persists a new history entry on pipeline_complete summary', () => {
    const { container } = render(
      <RunHistoryStrip onReplay={() => {}} summary={summary} scenario="showcase_rich" />,
    )
    // The entry persists after the first render.
    const stored = window.localStorage.getItem(STORAGE_KEY)
    expect(stored).not.toBeNull()
    const items = JSON.parse(stored!)
    expect(items).toHaveLength(1)
    expect(items[0].scenario).toBe('showcase_rich')
    expect(items[0].status).toBe('pass')
    // Rendered list shows the entry.
    expect(container.textContent).toContain('showcase_rich')
    expect(container.textContent).toContain('PASS')
  })

  it('caps history at 5 entries (FIFO eviction)', () => {
    const existing = Array.from({ length: 5 }).map((_, i) => ({
      id: `id-${i}`,
      runId: `run-${i}`,
      timestamp: new Date(2026, 4, 26, 10, i).toISOString(),
      scenario: 'demo_minimal' as const,
      status: 'pass' as const,
      wallClockS: 60 + i,
    }))
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(existing))
    render(
      <RunHistoryStrip onReplay={() => {}} summary={summary} scenario="showcase_rich" />,
    )
    const stored = JSON.parse(window.localStorage.getItem(STORAGE_KEY)!)
    expect(stored).toHaveLength(5)
    // Newest is first.
    expect(stored[0].scenario).toBe('showcase_rich')
    // Oldest (id-4) was evicted.
    expect(stored.find((it: { id: string }) => it.id === 'id-4')).toBeUndefined()
  })

  it('invokes onReplay with the entry scenario when Replay is clicked', () => {
    const onReplay = vi.fn()
    const { container } = render(
      <RunHistoryStrip onReplay={onReplay} summary={summary} scenario="showcase_rich" />,
    )
    const replayBtn = Array.from(container.querySelectorAll('button')).find(
      (b) => (b.textContent ?? '').trim() === 'Replay',
    )
    expect(replayBtn).toBeDefined()
    fireEvent.click(replayBtn!)
    expect(onReplay).toHaveBeenCalledWith(
      expect.objectContaining({ scenario: 'showcase_rich', skip_seed: true, reset: false }),
    )
  })

  it('Clear button empties history + localStorage', () => {
    const { container } = render(
      <RunHistoryStrip onReplay={() => {}} summary={summary} scenario="demo_minimal" />,
    )
    expect(window.localStorage.getItem(STORAGE_KEY)).not.toBeNull()
    const clearBtn = Array.from(container.querySelectorAll('button')).find(
      (b) => (b.textContent ?? '').trim() === 'Clear',
    )
    fireEvent.click(clearBtn!)
    const stored = window.localStorage.getItem(STORAGE_KEY)
    expect(stored).toBe('[]')
  })
})
