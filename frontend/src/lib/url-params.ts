/**
 * Safe readers for URL query-string state.
 *
 * The explorer pages treat the query string as the single source of truth for
 * filter / sort / page state, so a hand-edited, stale, or truncated URL can
 * carry a NaN page, a negative page, or an unknown enum value. These helpers
 * validate at the read boundary so a junk param degrades to a sane default
 * instead of reaching a hook (and the API) unverified.
 */

/**
 * Parse a `page` query param into a positive integer (>= 1).
 *
 * `null`, non-numeric, zero, negative, and fractional inputs all fall back to
 * `1`; a fractional input above 1 is floored (`"2.9"` -> `2`).
 */
export function parsePageParam(value: string | null): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed < 1) return 1
  return Math.floor(parsed)
}

/**
 * Parse a positive-integer ID query param (`store_id`, `product_id`, ...).
 *
 * Returns `undefined` for `null`, empty, non-numeric, fractional, or
 * non-positive input — never `NaN`.
 */
export function parseIdParam(value: string | null): number | undefined {
  if (value === null || value === '') return undefined
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed >= 1 ? parsed : undefined
}

/**
 * Return `value` only when it is a member of `allowed`; otherwise `undefined`.
 *
 * Use for enum-typed query params (status, model_type, sort_by, dimension, ...)
 * so an unknown value is dropped rather than blind-cast into a typed slot.
 */
export function parseEnumParam<T extends string>(
  value: string | null,
  allowed: readonly T[],
): T | undefined {
  return value !== null && (allowed as readonly string[]).includes(value)
    ? (value as T)
    : undefined
}
