/**
 * E5 (#411) — unit tests for useApprovalEvents. Stubs fetch to assert the
 * hook calls GET /demo/approval-events with the limit param and surfaces the
 * flattened response (pattern: use-workspaces.test.ts).
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createElement, type ReactNode } from 'react'

import { useApprovalEvents } from './use-approval-events'

function makeWrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client }, children)
  }
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useApprovalEvents', () => {
  it('GETs /demo/approval-events with the limit param and returns the events', async () => {
    const body = {
      events: [
        {
          workspace_id: 'a'.repeat(32),
          workspace_name: 'e5-story',
          action_id: 'act-1',
          tool_name: 'save_scenario',
          decision: 'approved',
          decided_at: '2026-06-01T12:05:00Z',
          session_id: 'sess-1',
          auto_approved: false,
          reason: null,
          execution_status: 'executed',
          transcript_summary: 'save it',
        },
      ],
      total: 1,
    }
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(body))
    vi.stubGlobal('fetch', fetchMock)

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => useApprovalEvents(25), {
      wrapper: makeWrapper(client),
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const url = String(fetchMock.mock.calls[0]![0])
    expect(url).toContain('/demo/approval-events')
    expect(url).toContain('limit=25')
    expect(result.current.data?.total).toBe(1)
    expect(result.current.data?.events[0]?.tool_name).toBe('save_scenario')
  })

  it('defaults the limit to 50', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ events: [], total: 0 }))
    vi.stubGlobal('fetch', fetchMock)

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => useApprovalEvents(), {
      wrapper: makeWrapper(client),
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(String(fetchMock.mock.calls[0]![0])).toContain('limit=50')
  })

  it('stays disabled when enabled=false', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    renderHook(() => useApprovalEvents(50, false), { wrapper: makeWrapper(client) })
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
