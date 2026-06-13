/**
 * Unit tests for the use-workspaces hooks.
 *
 * Stubs ``fetch`` to assert the hook issues a DELETE to the workspace
 * endpoint and invalidates the workspaces list on success; no real backend
 * is exercised (pattern: ``use-batches.test.ts``).
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createElement, type ReactNode } from 'react'

import {
  useDeleteWorkspace,
  usePatchWorkspace,
  useWorkspaceHealth,
  useWorkspaceLineage,
  useWorkspaces,
} from './use-workspaces'
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

// =============================================================================
// E2 (#408) — params-aware list + PATCH + health + lineage
// =============================================================================

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function problemResponse(detail: string, status: number): Response {
  return new Response(
    JSON.stringify({ type: '/errors/not-found', title: 'Not Found', status, detail }),
    { status, headers: { 'content-type': 'application/problem+json' } },
  )
}

describe('useWorkspaces (E2 params)', () => {
  it('serializes the list params onto the query string', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ workspaces: [], total: 0 }))
    vi.stubGlobal('fetch', fetchMock)

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(
      () =>
        useWorkspaces({
          q: 'demo',
          tags: 'smoke',
          include_archived: true,
          sort_by: 'name',
          sort_order: 'asc',
        }),
      { wrapper: makeWrapper(client) },
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const url = String(fetchMock.mock.calls[0]![0])
    expect(url).toContain('/demo/workspaces')
    expect(url).toContain('q=demo')
    expect(url).toContain('tags=smoke')
    expect(url).toContain('include_archived=true')
    expect(url).toContain('sort_by=name')
    expect(url).toContain('sort_order=asc')
  })

  it('omits unset params (legacy URL shape preserved)', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ workspaces: [], total: 0 }))
    vi.stubGlobal('fetch', fetchMock)

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => useWorkspaces(), { wrapper: makeWrapper(client) })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const url = String(fetchMock.mock.calls[0]![0])
    expect(url).toContain('limit=20')
    expect(url).not.toContain('q=')
    expect(url).not.toContain('include_archived')
    expect(url).not.toContain('sort_by')
  })
})

describe('usePatchWorkspace', () => {
  it('issues a PATCH with the partial body and invalidates the list', async () => {
    const workspaceId = 'a'.repeat(32)
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ workspace_id: workspaceId, pinned: true }))
    vi.stubGlobal('fetch', fetchMock)

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries')
    const { result } = renderHook(() => usePatchWorkspace(), {
      wrapper: makeWrapper(client),
    })

    await act(async () => {
      result.current.mutate({ workspaceId, update: { pinned: true } })
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const call = fetchMock.mock.calls[0]!
    expect(String(call[0])).toContain(`/demo/workspaces/${workspaceId}`)
    const init = call[1] as RequestInit
    expect(init.method).toBe('PATCH')
    expect(JSON.parse(String(init.body))).toEqual({ pinned: true })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['workspaces'] })
  })
})

describe('useWorkspaceHealth', () => {
  it('fetches the health endpoint for the loaded workspace', async () => {
    const workspaceId = 'a'.repeat(32)
    const health = {
      workspace_id: workspaceId,
      workspace_status: 'completed',
      partial_run: false,
      references: [],
      alive: 0,
      dead: 0,
      unknown: 0,
      checked_at: '2026-06-13T00:00:00Z',
    }
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(health))
    vi.stubGlobal('fetch', fetchMock)

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => useWorkspaceHealth(workspaceId), {
      wrapper: makeWrapper(client),
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(String(fetchMock.mock.calls[0]![0])).toContain(
      `/demo/workspaces/${workspaceId}/health`,
    )
    expect(result.current.data).toEqual(health)
  })

  it('stays disabled without a workspace id', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    renderHook(() => useWorkspaceHealth(''), { wrapper: makeWrapper(client) })
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('useWorkspaceLineage', () => {
  const idA = 'a'.repeat(32)
  const idB = 'b'.repeat(32)
  const idC = 'c'.repeat(32)

  function detailBody(id: string, name: string | null, parent: string | null) {
    return {
      workspace_id: id,
      name,
      replayed_from_workspace_id: parent,
      tags: [],
      archived: false,
      pinned: false,
    }
  }

  it('walks the chain newest → original and stops at the root', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(detailBody(idA, 'child', idB)))
      .mockResolvedValueOnce(jsonResponse(detailBody(idB, 'origin', null)))
    vi.stubGlobal('fetch', fetchMock)

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => useWorkspaceLineage(idA), {
      wrapper: makeWrapper(client),
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const lineage = result.current.data!
    expect(lineage.entries.map((e) => e.workspace_id)).toEqual([idA, idB])
    expect(lineage.entries.map((e) => e.deleted)).toEqual([false, false])
    expect(lineage.truncated).toBe(false)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('terminates the walk with a deleted sentinel on a 404 ancestor', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(detailBody(idA, 'child', idC)))
      .mockResolvedValueOnce(problemResponse(`Workspace not found: ${idC}`, 404))
    vi.stubGlobal('fetch', fetchMock)

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => useWorkspaceLineage(idA), {
      wrapper: makeWrapper(client),
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const lineage = result.current.data!
    expect(lineage.entries).toHaveLength(2)
    expect(lineage.entries[1]).toMatchObject({ workspace_id: idC, deleted: true, detail: null })
    expect(lineage.truncated).toBe(false)
  })

  it('caps the walk depth and flags truncation', async () => {
    // Every row points at another parent — an unbounded chain.
    const fetchMock = vi.fn().mockImplementation((url: unknown) => {
      const id = String(url).split('/').pop()!
      return Promise.resolve(jsonResponse(detailBody(id, null, 'f'.repeat(32))))
    })
    vi.stubGlobal('fetch', fetchMock)

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => useWorkspaceLineage(idA), {
      wrapper: makeWrapper(client),
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data!.entries).toHaveLength(5)
    expect(result.current.data!.truncated).toBe(true)
  })
})
