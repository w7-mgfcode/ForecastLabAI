import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { FeatureFramePanel } from './feature-frame-panel'

afterEach(cleanup)

describe('FeatureFramePanel', () => {
  it('renders pre-PRP-35 empty state when no fields are set', () => {
    render(<FeatureFramePanel />)
    expect(
      screen.getByText(/feature frame information not available/i),
    ).toBeTruthy()
  })

  it('renders the V1 chip + target-only note when version=1', () => {
    render(<FeatureFramePanel feature_frame_version={1} />)
    expect(
      screen.getByTestId('feature-frame-version-chip').textContent,
    ).toMatch(/V1/i)
    expect(screen.getByText(/target-only feature frame/i)).toBeTruthy()
  })

  it('renders the V2 chip and per-group collapsible rows when groups are supplied', () => {
    render(
      <FeatureFramePanel
        feature_frame_version={2}
        feature_groups={{
          target_history: ['target_history__lag_1', 'target_history__lag_7'],
          calendar: ['calendar__dow_sin'],
        }}
      />,
    )
    expect(
      screen.getByTestId('feature-frame-version-chip').textContent,
    ).toMatch(/V2/i)
    expect(screen.getByTestId('feature-frame-group-target_history')).toBeTruthy()
    expect(screen.getByTestId('feature-frame-group-calendar')).toBeTruthy()
  })

  it('surfaces the supplied-data warning when any safety class is unsafe_unless_supplied', () => {
    render(
      <FeatureFramePanel
        feature_frame_version={2}
        feature_groups={{ inventory: ['inventory__on_hand_qty'] }}
        feature_safety_classes={{
          'inventory__on_hand_qty': 'unsafe_unless_supplied',
        }}
      />,
    )
    expect(screen.getByTestId('feature-frame-safety-warning')).toBeTruthy()
  })

  it('omits the supplied-data warning when no column is unsafe', () => {
    render(
      <FeatureFramePanel
        feature_frame_version={2}
        feature_groups={{ target_history: ['target_history__lag_1'] }}
        feature_safety_classes={{
          'target_history__lag_1': 'safe',
        }}
      />,
    )
    expect(
      screen.queryByTestId('feature-frame-safety-warning'),
    ).toBeNull()
  })

  it('shows a loading state when isLoading=true', () => {
    render(<FeatureFramePanel isLoading />)
    expect(screen.getByText(/loading feature frame/i)).toBeTruthy()
  })
})
