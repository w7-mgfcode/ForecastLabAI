import { describe, expect, it } from 'vitest'
import {
  HORIZON_BUCKET_IDS,
  labelForBucket,
  sortBuckets,
} from './horizon-bucket-utils'

describe('labelForBucket', () => {
  it('returns operator-friendly labels for the four canonical buckets', () => {
    expect(labelForBucket('h_1_7')).toBe('Days 1-7')
    expect(labelForBucket('h_8_14')).toBe('Days 8-14')
    expect(labelForBucket('h_15_28')).toBe('Days 15-28')
    expect(labelForBucket('h_29_plus')).toBe('Days 29+')
  })

  it('surfaces unknown bucket ids verbatim', () => {
    expect(labelForBucket('h_30_60')).toBe('h_30_60')
  })
})

describe('sortBuckets', () => {
  it('returns the canonical order when all four ids are present, regardless of input order', () => {
    expect(sortBuckets(['h_29_plus', 'h_1_7', 'h_15_28', 'h_8_14'])).toEqual([
      ...HORIZON_BUCKET_IDS,
    ])
  })

  it('drops absent ids while preserving canonical order', () => {
    expect(sortBuckets(['h_29_plus', 'h_1_7'])).toEqual(['h_1_7', 'h_29_plus'])
  })

  it('appends unknown buckets at the end, alphabetically', () => {
    expect(
      sortBuckets(['h_30_60', 'h_1_7', 'h_8_14', 'h_zeta', 'h_alpha']),
    ).toEqual(['h_1_7', 'h_8_14', 'h_30_60', 'h_alpha', 'h_zeta'])
  })

  it('returns an empty array for empty input', () => {
    expect(sortBuckets([])).toEqual([])
  })
})
