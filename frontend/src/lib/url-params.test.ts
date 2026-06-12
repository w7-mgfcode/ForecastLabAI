import { describe, it, expect } from 'vitest'
import { parseEnumParam, parseIdParam, parsePageParam, parseTagsParam } from './url-params'

describe('parsePageParam', () => {
  it('returns the integer for a valid positive page', () => {
    expect(parsePageParam('3')).toBe(3)
  })

  it('floors a fractional page above 1', () => {
    expect(parsePageParam('2.9')).toBe(2)
  })

  it('falls back to 1 for null, non-numeric, zero, and negative input', () => {
    expect(parsePageParam(null)).toBe(1)
    expect(parsePageParam('')).toBe(1)
    expect(parsePageParam('abc')).toBe(1)
    expect(parsePageParam('0')).toBe(1)
    expect(parsePageParam('-4')).toBe(1)
  })
})

describe('parseIdParam', () => {
  it('returns a positive integer ID', () => {
    expect(parseIdParam('42')).toBe(42)
  })

  it('returns undefined for null, empty, non-numeric, fractional, or non-positive input', () => {
    expect(parseIdParam(null)).toBeUndefined()
    expect(parseIdParam('')).toBeUndefined()
    expect(parseIdParam('abc')).toBeUndefined()
    expect(parseIdParam('1.5')).toBeUndefined()
    expect(parseIdParam('0')).toBeUndefined()
    expect(parseIdParam('-3')).toBeUndefined()
  })
})

describe('parseEnumParam', () => {
  const allowed = ['asc', 'desc'] as const

  it('returns the value when it is a member of the allow-list', () => {
    expect(parseEnumParam('desc', allowed)).toBe('desc')
  })

  it('returns undefined for null or an unknown value', () => {
    expect(parseEnumParam(null, allowed)).toBeUndefined()
    expect(parseEnumParam('sideways', allowed)).toBeUndefined()
  })
})

describe('parseTagsParam', () => {
  it('returns an empty list for no params', () => {
    expect(parseTagsParam([])).toEqual([])
  })

  it('passes through namespaced tags untouched', () => {
    expect(parseTagsParam(['workspace:bf-demo'])).toEqual(['workspace:bf-demo'])
  })

  it('trims values and drops empty or whitespace-only entries', () => {
    expect(parseTagsParam(['  showcase ', '', '   '])).toEqual(['showcase'])
  })

  it('dedupes repeated tags', () => {
    expect(parseTagsParam(['price', 'price', ' price '])).toEqual(['price'])
  })

  it('caps the list at 20 entries', () => {
    const values = Array.from({ length: 50 }, (_, i) => `tag-${i}`)
    expect(parseTagsParam(values)).toHaveLength(20)
  })
})
