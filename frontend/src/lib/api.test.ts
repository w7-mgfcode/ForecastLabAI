import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api } from './api'

/** Build a fake `fetch` that returns one canned `Response`. */
function stubFetch(body: string, init: ResponseInit) {
  const fetchMock = vi.fn().mockResolvedValue(new Response(body, init))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('api()', () => {
  it('parses an RFC 7807 application/problem+json error body into ApiError.detail', async () => {
    // Regression: api() previously only treated `application/json` as JSON, so
    // `application/problem+json` error bodies went unparsed and the raw JSON
    // string leaked into the UI via getErrorMessage().
    const problem = {
      type: '/errors/bad-request',
      title: 'Bad Request',
      status: 400,
      detail: 'Need at least 7 observations',
      code: 'BAD_REQUEST',
    }
    stubFetch(JSON.stringify(problem), {
      status: 400,
      headers: { 'content-type': 'application/problem+json' },
    })

    const err = await api('/explain/forecast', { method: 'POST', body: {} }).catch(
      (e: unknown) => e,
    )

    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).status).toBe(400)
    expect((err as ApiError).message).toBe('Need at least 7 observations')
    expect((err as ApiError).detail?.detail).toBe('Need at least 7 observations')
  })

  it('parses a plain application/json success body', async () => {
    stubFetch(JSON.stringify({ status: 'ok' }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    })

    const data = await api<{ status: string }>('/health')

    expect(data).toEqual({ status: 'ok' })
  })
})
