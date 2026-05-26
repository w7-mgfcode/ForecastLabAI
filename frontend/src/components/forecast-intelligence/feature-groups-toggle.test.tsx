import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { FeatureGroupsToggle } from './feature-groups-toggle'
import type { FeatureGroup } from '@/types/api'

afterEach(cleanup)

const ALL_AVAILABLE: FeatureGroup[] = [
  'target_history',
  'rolling',
  'trend',
  'calendar',
  'price_promo',
  'lifecycle',
]
const DEFAULTS: FeatureGroup[] = [
  'target_history',
  'calendar',
  'rolling',
  'trend',
  'price_promo',
  'lifecycle',
]

describe('FeatureGroupsToggle', () => {
  it('renders a row per available group', () => {
    render(
      <FeatureGroupsToggle
        value={[]}
        onChange={() => {}}
        availableGroups={ALL_AVAILABLE}
        defaults={DEFAULTS}
      />,
    )
    for (const group of ALL_AVAILABLE) {
      expect(screen.getByTestId(`feature-groups-row-${group}`)).toBeTruthy()
    }
  })

  it('emits onChange with the group added when toggled on', () => {
    const onChange = vi.fn()
    render(
      <FeatureGroupsToggle
        value={[]}
        onChange={onChange}
        availableGroups={ALL_AVAILABLE}
        defaults={DEFAULTS}
      />,
    )
    const row = screen.getByTestId('feature-groups-row-target_history')
    const checkbox = row.querySelector('button[role="checkbox"]') as HTMLElement
    fireEvent.click(checkbox)
    expect(onChange).toHaveBeenCalledWith(['target_history'])
  })

  it('emits onChange with the group removed when toggled off', () => {
    const onChange = vi.fn()
    render(
      <FeatureGroupsToggle
        value={['target_history', 'rolling']}
        onChange={onChange}
        availableGroups={ALL_AVAILABLE}
        defaults={DEFAULTS}
      />,
    )
    const row = screen.getByTestId('feature-groups-row-target_history')
    const checkbox = row.querySelector('button[role="checkbox"]') as HTMLElement
    fireEvent.click(checkbox)
    expect(onChange).toHaveBeenCalledWith(['rolling'])
  })

  it('resets to defaults when "Use defaults" is clicked', () => {
    const onChange = vi.fn()
    render(
      <FeatureGroupsToggle
        value={[]}
        onChange={onChange}
        availableGroups={ALL_AVAILABLE}
        defaults={DEFAULTS}
      />,
    )
    fireEvent.click(screen.getByTestId('feature-groups-use-defaults'))
    expect(onChange).toHaveBeenCalledWith(DEFAULTS)
  })

  it('emits an empty array when "Clear" is clicked', () => {
    const onChange = vi.fn()
    render(
      <FeatureGroupsToggle
        value={['target_history']}
        onChange={onChange}
        availableGroups={ALL_AVAILABLE}
        defaults={DEFAULTS}
      />,
    )
    fireEvent.click(screen.getByTestId('feature-groups-clear'))
    expect(onChange).toHaveBeenCalledWith([])
  })

  it('renders a safety chip when safetyClasses surfaces an unsafe column for the group', () => {
    render(
      <FeatureGroupsToggle
        value={['inventory']}
        onChange={() => {}}
        availableGroups={['inventory']}
        defaults={[]}
        safetyClasses={{
          'inventory__on_hand_qty': 'unsafe_unless_supplied',
        }}
      />,
    )
    expect(screen.getByText(/requires supplied data/i)).toBeTruthy()
  })

  it('omits safety chip when safety_classes is not supplied', () => {
    render(
      <FeatureGroupsToggle
        value={[]}
        onChange={() => {}}
        availableGroups={['inventory']}
        defaults={[]}
      />,
    )
    // No safety badge anywhere in the row.
    const row = screen.getByTestId('feature-groups-row-inventory')
    expect(row.textContent).not.toMatch(/safe/i)
  })

  it('renders empty-state when availableGroups is empty', () => {
    render(
      <FeatureGroupsToggle
        value={[]}
        onChange={() => {}}
        availableGroups={[]}
        defaults={DEFAULTS}
      />,
    )
    expect(screen.getByText(/no feature groups/i)).toBeTruthy()
  })

  it('does not emit when disabled', () => {
    const onChange = vi.fn()
    render(
      <FeatureGroupsToggle
        value={[]}
        onChange={onChange}
        availableGroups={ALL_AVAILABLE}
        defaults={DEFAULTS}
        disabled
      />,
    )
    fireEvent.click(screen.getByTestId('feature-groups-use-defaults'))
    // Button is disabled at HTML level, so this is mostly a safety belt.
    expect(onChange).not.toHaveBeenCalled()
  })
})
