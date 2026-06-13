import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { CandidateModelPicker, MAX_CANDIDATES } from './candidate-model-picker'
import type { CandidateModelInfo, ModelCatalogResponse } from '@/types/api'

afterEach(cleanup)

function model(
  model_type: string,
  overrides: Partial<CandidateModelInfo> = {},
): CandidateModelInfo {
  return {
    model_type,
    label: model_type,
    family: 'baseline',
    feature_aware: false,
    requires_extra: false,
    default_params: {},
    supports_auto_predict: true,
    description: `desc ${model_type}`,
    enabled: true,
    ...overrides,
  }
}

const CATALOG: ModelCatalogResponse = {
  models: [
    model('naive'),
    model('regression', { family: 'tree', feature_aware: true }),
    model('lightgbm', { family: 'tree', feature_aware: true, requires_extra: true }),
    model('xgboost', { family: 'tree', feature_aware: true, requires_extra: true }),
  ],
  default_candidate_model_types: ['naive', 'regression'],
}

describe('CandidateModelPicker', () => {
  it('toggling a model calls onChange with the new selection', () => {
    const onChange = vi.fn()
    render(
      <CandidateModelPicker
        catalog={CATALOG}
        selected={['naive']}
        onChange={onChange}
        isLoading={false}
      />,
    )
    fireEvent.click(screen.getByTestId('candidate-checkbox-regression'))
    expect(onChange).toHaveBeenCalledWith(['naive', 'regression'])
  })

  it('deselects an already-selected model', () => {
    const onChange = vi.fn()
    render(
      <CandidateModelPicker
        catalog={CATALOG}
        selected={['naive', 'regression']}
        onChange={onChange}
        isLoading={false}
      />,
    )
    fireEvent.click(screen.getByTestId('candidate-checkbox-naive'))
    expect(onChange).toHaveBeenCalledWith(['regression'])
  })

  it('flags opt-in-extra models with an "extra" badge', () => {
    render(
      <CandidateModelPicker
        catalog={CATALOG}
        selected={[]}
        onChange={() => {}}
        isLoading={false}
      />,
    )
    expect(screen.getByTestId('candidate-extra-badge-lightgbm')).toBeTruthy()
    expect(screen.getByTestId('candidate-extra-badge-xgboost')).toBeTruthy()
    // A baseline model carries no extra badge.
    expect(screen.queryByTestId('candidate-extra-badge-naive')).toBeNull()
  })

  it('caps the selection at MAX_CANDIDATES and disables unselected models', () => {
    const many = Array.from({ length: MAX_CANDIDATES }, (_, i) => `m${i}`)
    const onChange = vi.fn()
    const bigCatalog: ModelCatalogResponse = {
      models: [...many.map((m) => model(m)), model('extra_model')],
      default_candidate_model_types: [],
    }
    render(
      <CandidateModelPicker
        catalog={bigCatalog}
        selected={many}
        onChange={onChange}
        isLoading={false}
      />,
    )
    expect(screen.getByTestId('candidate-cap-badge')).toBeTruthy()
    // Clicking an unselected model at the cap must NOT add it.
    fireEvent.click(screen.getByTestId('candidate-checkbox-extra_model'))
    expect(onChange).not.toHaveBeenCalled()
  })
})
