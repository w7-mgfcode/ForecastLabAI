import { afterEach, describe, expect, it, vi } from 'vitest'
import { safeRandomUUID } from './uuid-utils'

const V4_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('safeRandomUUID', () => {
  it('delegates to crypto.randomUUID when available', () => {
    vi.stubGlobal('crypto', {
      randomUUID: vi.fn(() => 'fixed-uuid'),
    } as unknown as Crypto)

    expect(safeRandomUUID()).toBe('fixed-uuid')
  })

  it('falls back to getRandomValues v4 when randomUUID is missing (LAN-HTTP shape)', () => {
    // The real plain-HTTP LAN shape: getRandomValues present, randomUUID absent (#332).
    vi.stubGlobal('crypto', {
      getRandomValues: globalThis.crypto.getRandomValues.bind(globalThis.crypto),
    } as unknown as Crypto)

    const first = safeRandomUUID()
    const second = safeRandomUUID()
    expect(first).toMatch(V4_REGEX)
    expect(second).toMatch(V4_REGEX)
    expect(first).not.toBe(second)
  })

  it('falls back to Math.random v4 when crypto is entirely absent', () => {
    vi.stubGlobal('crypto', undefined)

    const first = safeRandomUUID()
    const second = safeRandomUUID()
    expect(first).toMatch(V4_REGEX)
    expect(second).toMatch(V4_REGEX)
    expect(first).not.toBe(second)
  })
})
