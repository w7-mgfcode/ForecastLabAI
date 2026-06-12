import type { DemoRunRequest, WorkspaceListItem } from '@/types/api'

/**
 * E2 (#408) — the EXACT request a confirmed replay sends. Single source for
 * the confirm dialog's "Will send" column AND the page's executeReplay, so
 * the preview can never lie about what goes on the wire.
 */
export function buildReplayRequest(ws: WorkspaceListItem): DemoRunRequest {
  return {
    seed: ws.seed,
    scenario: ws.scenario,
    reset: ws.reset,
    skip_seed: ws.skip_seed,
    preservation: 'keep',
    // E1 (#407) — record replay lineage on the NEW row (soft reference).
    replayed_from_workspace_id: ws.workspace_id,
    ...(ws.name ? { workspace_name: ws.name } : {}),
  }
}
