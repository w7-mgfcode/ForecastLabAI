/**
 * Unit tests for use-batches hooks (PRP-34 ``useCancelBatch``).
 *
 * Stubs ``fetch`` to assert the hook issues a DELETE and updates the
 * TanStack Query cache; no real backend is exercised.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createElement, type ReactNode } from 'react'

import { useCancelBatch } from './use-batches'
import type { BatchSubmitResponse } from '@/types/api'

function makeSettledBatch(batch_id: string): BatchSubmitResponse {
  const now = '2026-05-25T00:00:00Z'
  return {
    batch_id,
    operation: 'backtest',
    status: 'cancelled',
    total_items: 4,
    completed_items: 0,
    failed_items: 0,
    running_items: 0,
    cancelled_items: 4,
    max_parallel: 4,
    effective_max_parallel: 4,
    started_at: now,
    completed_at: now,
    result_summary: { effective_max_parallel: 4 },
    created_at: now,
    updated_at: now,
  }
}

function makeWrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(
      QueryClientProvider,
      { client },
      children,
    )
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useCancelBatch', () => {
  it('issues a DELETE to /batch/{batchId} and updates the cache', async () => {
    const settled = makeSettledBatch('batch_abc')
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(settled), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const { result } = renderHook(() => useCancelBatch(), {
      wrapper: makeWrapper(client),
    })

    await act(async () => {
      result.current.mutate('batch_abc')
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    // Verifies the URL + HTTP method.
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const call = fetchMock.mock.calls[0]!
    expect(call[0]).toContain('/batch/batch_abc')
    expect((call[1] as RequestInit).method).toBe('DELETE')

    // Mutation success writes the settled parent into the per-batch cache
    // — ``useBatch(batchId)`` will read it immediately.
    expect(client.getQueryData(['batch', 'batch_abc'])).toEqual(settled)
  })

  it('surfaces an RFC 7807 problem+json failure as ApiError on the mutation', async () => {
    const problem = {
      type: '/errors/conflict',
      title: 'Conflict',
      status: 409,
      detail: 'Batch already terminal: completed',
      code: 'CONFLICT',
    }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(problem), {
          status: 409,
          headers: { 'content-type': 'application/problem+json' },
        }),
      ),
    )

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const { result } = renderHook(() => useCancelBatch(), {
      wrapper: makeWrapper(client),
    })

    await act(async () => {
      result.current.mutate('batch_terminal')
    })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(String(result.current.error)).toContain('Batch already terminal')
  })
})
