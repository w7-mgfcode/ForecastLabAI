import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { RunProgressPanel } from './run-progress-panel'
import type { CandidateProgress, SelectionProgress } from '@/types/api'

afterEach(cleanup)

const progress: SelectionProgress = {
  total: 3,
  pending: 1,
  running: 1,
  completed: 1,
  failed: 0,
  cancelled: 0,
}

function cand(model_type: string, status: CandidateProgress['status']): CandidateProgress {
  return {
    candidate_id: `id-${model_type}`,
    ordinal: 0,
    model_type,
    status,
    error: status === 'failed' ? 'boom' : null,
    started_at: null,
    completed_at: null,
    duration_ms: status === 'completed' ? 1500 : null,
  }
}

describe('RunProgressPanel', () => {
  it('renders status badge, counts, and a per-candidate row', () => {
    render(
      <RunProgressPanel
        status="running"
        progress={progress}
        candidates={[cand('naive', 'completed'), cand('regression', 'running')]}
      />,
    )
    expect(screen.getByTestId('run-status-badge').textContent).toContain('running')
    expect(screen.getByText('Total')).toBeTruthy()
    expect(screen.getByTestId('candidate-row-naive')).toBeTruthy()
    expect(screen.getByTestId('candidate-row-regression')).toBeTruthy()
  })

  it('keeps a failed candidate visible with its error', () => {
    render(
      <RunProgressPanel
        status="partial"
        progress={progress}
        candidates={[cand('xgboost', 'failed')]}
      />,
    )
    const row = screen.getByTestId('candidate-row-xgboost')
    expect(row.textContent).toContain('failed')
    expect(row.textContent).toContain('boom')
  })
})
