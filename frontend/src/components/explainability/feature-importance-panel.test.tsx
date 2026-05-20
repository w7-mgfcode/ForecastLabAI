import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { ApiError } from '@/lib/api'
import { FeatureImportancePanel } from './feature-importance-panel'

afterEach(cleanup)
import type {
  FeatureImportanceItem,
  FeatureMetadataResponse,
} from '@/types/api'

const treeItems: FeatureImportanceItem[] = [
  { name: 'price_factor', importance: 120.5, kind: 'tree', rank: 1 },
  { name: 'lag_7', importance: 80.2, kind: 'tree', rank: 2 },
  { name: 'is_holiday', importance: 30.1, kind: 'tree', rank: 3 },
]

const linearItems: FeatureImportanceItem[] = [
  { name: 'price_factor', importance: 2.3, kind: 'linear_coef', rank: 1 },
  { name: 'is_holiday', importance: -1.7, kind: 'linear_coef', rank: 2 },
  { name: 'promo_active', importance: 0.4, kind: 'linear_coef', rank: 3 },
]

const sampleTree: FeatureMetadataResponse = {
  run_id: 'run-tree',
  model_type: 'lightgbm',
  model_family: 'tree',
  feature_columns: treeItems.map((i) => i.name),
  features: treeItems,
  importance_type: 'split',
}

const sampleLinear: FeatureMetadataResponse = {
  run_id: 'run-additive',
  model_type: 'prophet_like',
  model_family: 'additive',
  feature_columns: linearItems.map((i) => i.name),
  features: linearItems,
  importance_type: 'ridge_coef',
}

describe('FeatureImportancePanel', () => {
  it('renders tree-kind items with positive bars and primary colour', () => {
    render(<FeatureImportancePanel data={sampleTree} />)
    expect(screen.getByText('Feature Importance')).toBeTruthy()
    const rows = screen.getAllByTestId('feature-importance-row')
    expect(rows.length).toBe(treeItems.length)
    // All rows are tree-kind.
    rows.forEach((row) => {
      expect(row.getAttribute('data-kind')).toBe('tree')
    })
    // The importance_type tag renders ("split" for the LightGBM default).
    expect(screen.getByText('split')).toBeTruthy()
    // The verbatim correlation-vs-causation caveat is present.
    expect(
      screen.getByText(/Importance is model-derived. It reflects how much each feature/),
    ).toBeTruthy()
  })

  it('renders linear-coef items with signed values', () => {
    render(<FeatureImportancePanel data={sampleLinear} />)
    const rows = screen.getAllByTestId('feature-importance-row')
    rows.forEach((row) => {
      expect(row.getAttribute('data-kind')).toBe('linear_coef')
    })
    // The negative coefficient renders with its sign preserved.
    expect(screen.getByText(/-1\.700/)).toBeTruthy()
    // The positive coefficients render with the right magnitude.
    expect(screen.getByText(/2\.300/)).toBeTruthy()
    // The additive family description is present.
    expect(
      screen.getByText(/Additive Ridge coefficients\. Sign indicates direction/),
    ).toBeTruthy()
  })

  it('renders a loading state', () => {
    render(<FeatureImportancePanel isLoading />)
    expect(screen.getByText(/Loading feature importance/)).toBeTruthy()
  })

  it('renders a neutral message for a 400 (baseline family)', () => {
    const apiError = new ApiError('baseline only', 400)
    render(<FeatureImportancePanel error={apiError} />)
    expect(screen.getByText(/tree and additive model families only/)).toBeTruthy()
  })

  it('renders a neutral message for a 422 (no artifact / missing extra)', () => {
    const apiError = new ApiError('no artifact', 422)
    render(<FeatureImportancePanel error={apiError} />)
    expect(
      screen.getByText(/available once training completes and the artifact is saved/),
    ).toBeTruthy()
  })

  it('renders a destructive message for an unexpected error', () => {
    render(<FeatureImportancePanel error={new Error('boom')} />)
    expect(screen.getByText('boom')).toBeTruthy()
  })

  it('renders an empty-features neutral message', () => {
    render(
      <FeatureImportancePanel
        data={{ ...sampleTree, features: [], feature_columns: [] }}
      />,
    )
    expect(
      screen.getByText(/No feature importance values are available/),
    ).toBeTruthy()
  })
})
