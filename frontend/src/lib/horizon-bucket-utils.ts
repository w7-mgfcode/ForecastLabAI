/**
 * PRP-37 Slice C — Per-horizon-bucket helpers.
 *
 * PRP-36 partitions a backtest fold into four operator-meaningful buckets
 * ('h_1_7' / 'h_8_14' / 'h_15_28' / 'h_29_plus') so the UI can show how
 * forecast error behaves over near vs. far horizons. The bucket id set is
 * fixed by the backend (`app/features/backtesting/metrics.py`), but
 * empty buckets are dropped from the response — sort defensively.
 */

/** The four bucket ids the backend may emit. */
export const HORIZON_BUCKET_IDS = [
  'h_1_7',
  'h_8_14',
  'h_15_28',
  'h_29_plus',
] as const

export type HorizonBucketId = (typeof HORIZON_BUCKET_IDS)[number]

const BUCKET_LABELS: Record<HorizonBucketId, string> = {
  h_1_7: 'Days 1-7',
  h_8_14: 'Days 8-14',
  h_15_28: 'Days 15-28',
  h_29_plus: 'Days 29+',
}

/** UI label for a known bucket id; unknown ids surface verbatim. */
export function labelForBucket(id: string): string {
  return BUCKET_LABELS[id as HorizonBucketId] ?? id
}

/**
 * Return `ids` sorted into a stable, operator-friendly order matching
 * {@link HORIZON_BUCKET_IDS}; unknown bucket ids are appended at the end
 * (alphabetical) so a forward-compatible bucket from a newer backend
 * still renders.
 */
export function sortBuckets(ids: string[]): string[] {
  const known: string[] = []
  const unknown: string[] = []
  for (const id of HORIZON_BUCKET_IDS) {
    if (ids.includes(id)) known.push(id)
  }
  for (const id of ids) {
    if (!(HORIZON_BUCKET_IDS as readonly string[]).includes(id)) {
      unknown.push(id)
    }
  }
  unknown.sort()
  return [...known, ...unknown]
}
