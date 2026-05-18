// Pure, React-free helpers for the Knowledge page. Kept separate from the page
// component so they are cheap to unit-test (see knowledge-utils.test.ts) —
// mirrors the use-demo-pipeline.ts / status-utils.ts precedent.
import type { RagSource, ChunkResult } from '@/types/api'

/**
 * Convert a relevance score (0..1) into a display percentage string.
 * Non-finite or out-of-range inputs are clamped: 0.873 -> "87%",
 * 1.4 -> "100%", -0.2 -> "0%".
 */
export function formatRelevance(score: number): string {
  const safe = Number.isFinite(score) ? score : 0
  const clamped = Math.min(1, Math.max(0, safe))
  return `${Math.round(clamped * 100)}%`
}

/**
 * Group indexed sources by their source_type (e.g. "markdown", "openapi").
 * An empty array yields an empty object; a missing type falls back to "unknown".
 */
export function groupSourcesByType(sources: RagSource[]): Record<string, RagSource[]> {
  const groups: Record<string, RagSource[]> = {}
  for (const source of sources) {
    const key = source.source_type || 'unknown'
    if (!groups[key]) {
      groups[key] = []
    }
    groups[key].push(source)
  }
  return groups
}

/**
 * Single-line excerpt of a chunk's content for a result card. Collapses runs of
 * whitespace and truncates with an ellipsis past `maxChars` (default 240).
 */
export function chunkExcerpt(chunk: ChunkResult, maxChars = 240): string {
  const collapsed = chunk.content.replace(/\s+/g, ' ').trim()
  if (collapsed.length <= maxChars) {
    return collapsed
  }
  return `${collapsed.slice(0, maxChars).trimEnd()}…`
}
