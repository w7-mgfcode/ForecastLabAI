import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { BatchMatrixPicker } from './batch-matrix-picker'
import type { FeatureGroup } from '@/types/api'

afterEach(cleanup)

const MODELS = ['naive', 'lightgbm', 'regression']
const GROUPS: FeatureGroup[] = ['target_history', 'calendar', 'rolling']
const DEFAULTS: FeatureGroup[] = ['target_history', 'calendar', 'rolling']

describe('BatchMatrixPicker', () => {
  it('adds a V1 row when the cell is toggled on', () => {
    const onChange = vi.fn()
    render(
      <BatchMatrixPicker
        availableModels={MODELS}
        availableGroups={GROUPS}
        defaults={DEFAULTS}
        value={[]}
        onChange={onChange}
      />,
    )
    fireEvent.click(screen.getByTestId('batch-matrix-cell-naive-v1'))
    expect(onChange).toHaveBeenCalledWith([
      {
        model_type: 'naive',
        feature_frame_version: 1,
        feature_groups: [],
      },
    ])
  })

  it('adds a V2 row pre-populated with defaults', () => {
    const onChange = vi.fn()
    render(
      <BatchMatrixPicker
        availableModels={MODELS}
        availableGroups={GROUPS}
        defaults={DEFAULTS}
        value={[]}
        onChange={onChange}
      />,
    )
    fireEvent.click(screen.getByTestId('batch-matrix-cell-lightgbm-v2'))
    expect(onChange).toHaveBeenCalledWith([
      {
        model_type: 'lightgbm',
        feature_frame_version: 2,
        feature_groups: DEFAULTS,
      },
    ])
  })

  it('removes a row when its cell is toggled off', () => {
    const onChange = vi.fn()
    render(
      <BatchMatrixPicker
        availableModels={MODELS}
        availableGroups={GROUPS}
        defaults={DEFAULTS}
        value={[
          {
            model_type: 'naive',
            feature_frame_version: 1,
            feature_groups: [],
          },
        ]}
        onChange={onChange}
      />,
    )
    fireEvent.click(screen.getByTestId('batch-matrix-cell-naive-v1'))
    expect(onChange).toHaveBeenCalledWith([])
  })

  it('surfaces the max-rows badge and disables new cells when the cap is hit', () => {
    const value = MODELS.map((model_type) => ({
      model_type,
      feature_frame_version: 1 as const,
      feature_groups: [],
    }))
    render(
      <BatchMatrixPicker
        availableModels={MODELS}
        availableGroups={GROUPS}
        defaults={DEFAULTS}
        value={value}
        onChange={() => {}}
        max_rows={3}
      />,
    )
    expect(screen.getByTestId('batch-matrix-limit-badge')).toBeTruthy()
    // An unchecked V2 cell is disabled because we cannot add more rows.
    expect(
      screen
        .getByTestId('batch-matrix-cell-lightgbm-v2')
        .hasAttribute('disabled'),
    ).toBe(true)
  })

  it('renders a per-row group editor only for V2 rows', () => {
    render(
      <BatchMatrixPicker
        availableModels={MODELS}
        availableGroups={GROUPS}
        defaults={DEFAULTS}
        value={[
          {
            model_type: 'regression',
            feature_frame_version: 2,
            feature_groups: DEFAULTS,
          },
          {
            model_type: 'naive',
            feature_frame_version: 1,
            feature_groups: [],
          },
        ]}
        onChange={() => {}}
      />,
    )
    expect(
      screen.getByTestId('batch-matrix-row-config-regression'),
    ).toBeTruthy()
    expect(
      screen.queryByTestId('batch-matrix-row-config-naive'),
    ).toBeNull()
  })
})
