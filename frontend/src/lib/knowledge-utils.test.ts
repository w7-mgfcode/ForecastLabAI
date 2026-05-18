import { describe, it, expect } from 'vitest'
import { formatRelevance, groupSourcesByType, chunkExcerpt } from './knowledge-utils'
import type { RagSource, ChunkResult } from '@/types/api'

/** Build a RagSource with sensible defaults for the fields not under test. */
function makeSource(partial: Partial<RagSource> & Pick<RagSource, 'source_id'>): RagSource {
  return {
    source_id: partial.source_id,
    source_type: partial.source_type ?? 'markdown',
    source_path: partial.source_path ?? 'docs/example.md',
    chunk_count: partial.chunk_count ?? 3,
    content_hash: partial.content_hash ?? 'hash',
    indexed_at: partial.indexed_at ?? '2026-05-18T00:00:00Z',
    metadata: partial.metadata ?? null,
  }
}

/** Build a ChunkResult with sensible defaults for the fields not under test. */
function makeChunk(partial: Partial<ChunkResult> & Pick<ChunkResult, 'content'>): ChunkResult {
  return {
    chunk_id: partial.chunk_id ?? 'chunk-1',
    source_id: partial.source_id ?? 'src-1',
    source_path: partial.source_path ?? 'docs/example.md',
    source_type: partial.source_type ?? 'markdown',
    content: partial.content,
    relevance_score: partial.relevance_score ?? 0.8,
    metadata: partial.metadata ?? null,
  }
}

describe('formatRelevance', () => {
  it('renders a score as a rounded percentage', () => {
    expect(formatRelevance(0.873)).toBe('87%')
  })

  it('clamps the endpoints', () => {
    expect(formatRelevance(0)).toBe('0%')
    expect(formatRelevance(1)).toBe('100%')
  })

  it('clamps out-of-range values', () => {
    expect(formatRelevance(1.4)).toBe('100%')
    expect(formatRelevance(-0.2)).toBe('0%')
  })

  it('treats a non-finite score as zero', () => {
    expect(formatRelevance(Number.NaN)).toBe('0%')
    expect(formatRelevance(Number.POSITIVE_INFINITY)).toBe('0%')
  })
})

describe('groupSourcesByType', () => {
  it('groups a mixed source list into per-type buckets', () => {
    const groups = groupSourcesByType([
      makeSource({ source_id: 'a', source_type: 'markdown' }),
      makeSource({ source_id: 'b', source_type: 'openapi' }),
      makeSource({ source_id: 'c', source_type: 'markdown' }),
    ])
    expect(Object.keys(groups).sort()).toEqual(['markdown', 'openapi'])
    expect(groups.markdown).toHaveLength(2)
    expect(groups.openapi).toHaveLength(1)
  })

  it('returns an empty object for an empty array', () => {
    expect(groupSourcesByType([])).toEqual({})
  })

  it('falls back to "unknown" for a blank source_type', () => {
    const groups = groupSourcesByType([makeSource({ source_id: 'a', source_type: '' })])
    expect(groups.unknown).toHaveLength(1)
  })
})

describe('chunkExcerpt', () => {
  it('returns short content intact with collapsed whitespace', () => {
    const chunk = makeChunk({ content: '  hello   world\n\tagain  ' })
    expect(chunkExcerpt(chunk)).toBe('hello world again')
  })

  it('truncates long content with an ellipsis', () => {
    const chunk = makeChunk({ content: 'x'.repeat(500) })
    const excerpt = chunkExcerpt(chunk)
    expect(excerpt.endsWith('…')).toBe(true)
    expect(excerpt.length).toBeLessThanOrEqual(241)
  })

  it('honours a custom maxChars', () => {
    const chunk = makeChunk({ content: 'abcdefghij' })
    expect(chunkExcerpt(chunk, 5)).toBe('abcde…')
  })
})
