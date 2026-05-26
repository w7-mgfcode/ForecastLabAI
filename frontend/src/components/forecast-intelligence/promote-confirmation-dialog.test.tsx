import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest'
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { PromoteConfirmationDialog } from './promote-confirmation-dialog'
import type { ArtifactVerifyResponse, ModelRun } from '@/types/api'

function makeRun(overrides: Partial<ModelRun> = {}): ModelRun {
  return {
    run_id: 'run_aaaaaaaaaaaa',
    status: 'success',
    model_type: 'lightgbm',
    model_family: 'tree',
    model_config: {},
    feature_config: null,
    config_hash: 'h',
    data_window_start: '2024-01-01',
    data_window_end: '2024-06-30',
    store_id: 1,
    product_id: 1,
    metrics: { wape: 12.0 },
    artifact_uri: 'file:///artifact.joblib',
    artifact_hash: 'abc',
    artifact_size_bytes: 1024,
    runtime_info: null,
    agent_context: null,
    git_sha: null,
    error_message: null,
    started_at: '2024-01-01',
    completed_at: '2024-01-02',
    created_at: '2024-01-01',
    updated_at: '2024-01-01',
    ...overrides,
  }
}

function makeWrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client }, children)
  }
}

function stubVerify(response: ArtifactVerifyResponse) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(response), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

beforeEach(() => {
  cleanup()
})

afterEach(() => {
  vi.unstubAllGlobals()
  cleanup()
})

describe('PromoteConfirmationDialog', () => {
  it('enables Promote when verify ok, no worse-WAPE, no V mismatch, alias name set', async () => {
    stubVerify({
      verified: true,
      run_id: 'r',
      artifact_uri: 'u',
      computed_hash: 'abc',
      stored_hash: 'abc',
    })
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const run = makeRun({ feature_frame_version: 2 })
    const champion = makeRun({
      run_id: 'champ',
      metrics: { wape: 15.0 },
      feature_frame_version: 2,
    })
    render(
      <PromoteConfirmationDialog
        open
        onOpenChange={() => {}}
        run={run}
        currentChampion={champion}
        defaultAliasName="production"
        onConfirm={() => Promise.resolve()}
      />,
      { wrapper: makeWrapper(client) },
    )
    await waitFor(() =>
      expect(
        screen
          .getByTestId('promote-confirmation-action')
          .hasAttribute('disabled'),
      ).toBe(false),
    )
  })

  it('blocks Promote when artifact verify fails (no checkbox can override)', async () => {
    stubVerify({
      verified: false,
      run_id: 'r',
      artifact_uri: 'u',
      computed_hash: 'BAD',
      stored_hash: 'abc',
      error: 'checksum mismatch',
    })
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    render(
      <PromoteConfirmationDialog
        open
        onOpenChange={() => {}}
        run={makeRun()}
        defaultAliasName="production"
        onConfirm={() => Promise.resolve()}
      />,
      { wrapper: makeWrapper(client) },
    )
    await waitFor(() =>
      expect(
        screen.queryByTestId('promote-confirmation-verify-failed'),
      ).toBeTruthy(),
    )
    expect(
      screen
        .getByTestId('promote-confirmation-action')
        .hasAttribute('disabled'),
    ).toBe(true)
  })

  it('requires the worse-WAPE checkbox when latest WAPE > champion WAPE', async () => {
    stubVerify({
      verified: true,
      run_id: 'r',
      artifact_uri: 'u',
      computed_hash: 'abc',
      stored_hash: 'abc',
    })
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const run = makeRun({ metrics: { wape: 20.0 } })
    const champion = makeRun({
      run_id: 'champ',
      metrics: { wape: 12.0 },
    })
    render(
      <PromoteConfirmationDialog
        open
        onOpenChange={() => {}}
        run={run}
        currentChampion={champion}
        defaultAliasName="production"
        onConfirm={() => Promise.resolve()}
      />,
      { wrapper: makeWrapper(client) },
    )
    await waitFor(() =>
      expect(
        screen.getByTestId('promote-confirmation-worse-wape'),
      ).toBeTruthy(),
    )
    // Action disabled while warning unacknowledged.
    expect(
      screen
        .getByTestId('promote-confirmation-action')
        .hasAttribute('disabled'),
    ).toBe(true)
    // Acknowledge → action enabled.
    fireEvent.click(screen.getByTestId('promote-confirmation-worse-ack'))
    await waitFor(() =>
      expect(
        screen
          .getByTestId('promote-confirmation-action')
          .hasAttribute('disabled'),
      ).toBe(false),
    )
  })

  it('requires the V-mismatch checkbox when champion V differs from run V', async () => {
    stubVerify({
      verified: true,
      run_id: 'r',
      artifact_uri: 'u',
      computed_hash: 'abc',
      stored_hash: 'abc',
    })
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const run = makeRun({ feature_frame_version: 2 })
    const champion = makeRun({
      run_id: 'champ',
      feature_frame_version: 1,
    })
    render(
      <PromoteConfirmationDialog
        open
        onOpenChange={() => {}}
        run={run}
        currentChampion={champion}
        defaultAliasName="production"
        onConfirm={() => Promise.resolve()}
      />,
      { wrapper: makeWrapper(client) },
    )
    await waitFor(() =>
      expect(
        screen.getByTestId('promote-confirmation-version-mismatch'),
      ).toBeTruthy(),
    )
    expect(
      screen
        .getByTestId('promote-confirmation-action')
        .hasAttribute('disabled'),
    ).toBe(true)
    fireEvent.click(screen.getByTestId('promote-confirmation-version-ack'))
    await waitFor(() =>
      expect(
        screen
          .getByTestId('promote-confirmation-action')
          .hasAttribute('disabled'),
      ).toBe(false),
    )
  })
})
