/**
 * Unit tests for the use-workspaces hooks (``useDeleteWorkspace``).
 *
 * Stubs ``fetch`` to assert the hook issues a DELETE to the workspace
 * endpoint and invalidates the workspaces list on success; no real backend
 * is exercised (pattern: ``use-batches.test.ts``).
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createElement, type ReactNode } from 'react'

import { useDeleteWorkspace } from './use-workspaces'
import { ApiError } from '@/lib/api'

function makeWrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client }, children)
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useDeleteWorkspace', () => {
  it('issues a DELETE to /demo/workspaces/{id} and invalidates the list', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries')
    const { result } = renderHook(() => useDeleteWorkspace(), {
      wrapper: makeWrapper(client),
    })

    const workspaceId = 'a'.repeat(32)
    await act(async () => {
      result.current.mutate(workspaceId)
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const call = fetchMock.mock.calls[0]!
    expect(String(call[0])).toContain(`/demo/workspaces/${workspaceId}`)
    expect((call[1] as RequestInit).method).toBe('DELETE')

    // Success invalidates every ['workspaces', ...] query — the panel list
    // refetches and the deleted row disappears.
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['workspaces'] })
  })

  it('surfaces an RFC 7807 404 as ApiError on the mutation', async () => {
    const problem = {
      type: '/errors/not-found',
      title: 'Not Found',
      status: 404,
      detail: 'Workspace not found: ' + 'f'.repeat(32),
      code: 'NOT_FOUND',
    }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(problem), {
          status: 404,
          headers: { 'content-type': 'application/problem+json' },
        }),
      ),
    )

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const { result } = renderHook(() => useDeleteWorkspace(), {
      wrapper: makeWrapper(client),
    })

    await act(async () => {
      result.current.mutate('f'.repeat(32))
    })
    await waitFor(() => expect(result.current.isError).toBe(true))

    const error = result.current.error
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(404)
    expect((error as ApiError).message).toContain('Workspace not found')
  })
})
