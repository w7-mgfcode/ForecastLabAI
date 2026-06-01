import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { TrainForecastActions } from './train-forecast-actions'

afterEach(cleanup)

describe('TrainForecastActions', () => {
  it('shows the blocked state for a feature-aware winner', () => {
    render(
      <TrainForecastActions
        supportsAutoPredict={false}
        trained
        isPredicting={false}
        onForecast={() => {}}
      />,
    )
    expect(screen.getByTestId('forecast-blocked-state').textContent).toContain(
      'What-If Planner',
    )
    expect(screen.queryByTestId('forecast-button')).toBeNull()
  })

  it('fires onForecast when the trained forecast button is clicked', () => {
    const onForecast = vi.fn()
    render(
      <TrainForecastActions
        supportsAutoPredict
        trained
        isPredicting={false}
        onForecast={onForecast}
      />,
    )
    fireEvent.click(screen.getByTestId('forecast-button'))
    expect(onForecast).toHaveBeenCalledOnce()
  })

  it('disables the forecast button until a model is trained', () => {
    render(
      <TrainForecastActions
        supportsAutoPredict
        trained={false}
        isPredicting={false}
        onForecast={() => {}}
      />,
    )
    expect(screen.getByTestId('forecast-button').hasAttribute('disabled')).toBe(true)
  })
})
