import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { RankingTable } from './ranking-table'
import type { ModelRankEntry } from '@/types/api'

afterEach(cleanup)

const ranking: ModelRankEntry[] = [
  {
    rank: 1,
    model_type: 'regression',
    params: {},
    included: true,
    exclusion_reason: null,
    metrics: { wape: 10, smape: 8, mae: 4, bias: 0.1 },
  },
  {
    rank: 2,
    model_type: 'naive',
    params: {},
    included: true,
    exclusion_reason: null,
    metrics: { wape: 14, smape: 12, mae: 6, bias: 0.5 },
  },
  {
    rank: null,
    model_type: 'moving_average',
    params: { window_size: 0 },
    included: false,
    exclusion_reason: 'failed',
    metrics: null,
  },
]

describe('RankingTable', () => {
  it('renders a row per entry; excluded rows show their reason', () => {
    render(<RankingTable ranking={ranking} onSelectModel={() => {}} />)
    expect(screen.getByTestId('ranking-row-regression')).toBeTruthy()
    expect(screen.getByTestId('ranking-row-naive')).toBeTruthy()
    const excluded = screen.getByTestId('ranking-row-moving_average')
    expect(excluded.textContent).toContain('failed')
  })

  it('calls onSelectModel with the clicked entry', () => {
    const onSelect = vi.fn()
    render(<RankingTable ranking={ranking} onSelectModel={onSelect} />)
    fireEvent.click(screen.getByTestId('ranking-row-naive'))
    expect(onSelect).toHaveBeenCalledWith(ranking[1])
  })
})
