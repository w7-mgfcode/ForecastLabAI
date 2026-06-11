/**
 * #332 — crypto.randomUUID() exists only in secure contexts (HTTPS or localhost).
 * On a plain-HTTP LAN origin (the showcase dogfood setup) it is undefined and a direct
 * call TypeErrors. crypto.getRandomValues is NOT secure-context-gated, so the fallback
 * keeps cryptographically-strong entropy; Math.random is a last resort for environments
 * with no Web Crypto at all (ids here are React keys / history ids, not security tokens).
 */
export function safeRandomUUID(): string {
  // eslint-disable-next-line no-restricted-properties -- feature-detecting the restricted member
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    // eslint-disable-next-line no-restricted-properties -- the one sanctioned call site
    return crypto.randomUUID()
  }
  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    const bytes = new Uint8Array(16)
    crypto.getRandomValues(bytes)
    bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x40 // version 4
    bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80 // variant 10xx
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
  }
  // No Web Crypto at all — uniqueness only, not cryptographic strength.
  let uuid = ''
  for (let i = 0; i < 36; i++) {
    if (i === 8 || i === 13 || i === 18 || i === 23) uuid += '-'
    else if (i === 14) uuid += '4'
    else if (i === 19) uuid += (((Math.random() * 4) | 0) | 8).toString(16) // 8,9,a,b
    else uuid += ((Math.random() * 16) | 0).toString(16)
  }
  return uuid
}
