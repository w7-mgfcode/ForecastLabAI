import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { WinnerCard } from './winner-card'
import type { WinnerSummary } from '@/types/api'

afterEach(cleanup)

const winner: WinnerSummary = {
  model_type: 'regression',
  params: {},
  metrics: { wape: 10, smape: 8, mae: 4, bias: 0.1 },
  rank: 1,
}

describe('WinnerCard', () => {
  it('renders the winner, confidence, metrics, and bias copy', () => {
    render(<WinnerCard winner={winner} confidence="high" reasons={['clear lead']} />)
    expect(screen.getByTestId('winner-card').textContent).toContain('regression')
    expect(screen.getByTestId('winner-confidence-badge').textContent).toContain('high')
    expect(screen.getByText('clear lead')).toBeTruthy()
    expect(screen.getByText(/Positive bias means the model under-forecasts/)).toBeTruthy()
  })

  it('renders a no-winner state when winner is null', () => {
    render(<WinnerCard winner={null} confidence={null} reasons={[]} />)
    expect(screen.getByText('No champion selected')).toBeTruthy()
  })

  it('surfaces the deterministic business_summary headline read-only', () => {
    render(
      <WinnerCard
        winner={winner}
        confidence="medium"
        reasons={[]}
        businessSummary={{ headline: 'regression wins by 28% WAPE' }}
      />,
    )
    expect(screen.getByText('regression wins by 28% WAPE')).toBeTruthy()
  })
})
