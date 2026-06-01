import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { WinnerDecisionPanel } from './winner-decision-panel'
import type { TrainWinnerResponse } from '@/types/api'

afterEach(cleanup)

describe('WinnerDecisionPanel', () => {
  it('trains the recommended winner without a confirm dialog', () => {
    const onTrain = vi.fn()
    render(
      <WinnerDecisionPanel
        winnerModelType="naive"
        candidateModelTypes={['naive', 'seasonal_naive']}
        isTraining={false}
        trainResult={null}
        onTrain={onTrain}
      />,
    )
    expect(screen.getByTestId('decision-train-button').textContent).toContain(
      'Train recommended',
    )
    fireEvent.click(screen.getByTestId('decision-train-button'))
    expect(onTrain).toHaveBeenCalledWith('naive', null)
  })

  it('renders the override warning from a train result', () => {
    const trainResult: TrainWinnerResponse = {
      selection_id: 's',
      model_type: 'seasonal_naive',
      model_path: 'p',
      is_override: true,
      override_warning: 'You trained seasonal_naive instead of naive.',
    }
    render(
      <WinnerDecisionPanel
        winnerModelType="naive"
        candidateModelTypes={['naive', 'seasonal_naive']}
        isTraining={false}
        trainResult={trainResult}
        onTrain={() => {}}
      />,
    )
    expect(screen.getByTestId('decision-override-warning').textContent).toContain(
      'seasonal_naive',
    )
  })
})
