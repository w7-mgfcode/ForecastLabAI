import type { DemoRunRequest, WorkspaceListItem } from '@/types/api'
import { parseRunConfig } from './run-config-utils'

/**
 * E2 (#408) — the EXACT request a confirmed replay sends. Single source for
 * the confirm dialog's "Will send" column AND the page's executeReplay, so
 * the preview can never lie about what goes on the wire.
 */
export function buildReplayRequest(ws: WorkspaceListItem): DemoRunRequest {
  // E4 (#410) — replay-verbatim covers the recorded run config; null on
  // default-config rows, so their replay frame stays byte-identical.
  const runConfig = parseRunConfig(ws.run_config)
  return {
    seed: ws.seed,
    scenario: ws.scenario,
    reset: ws.reset,
    skip_seed: ws.skip_seed,
    preservation: 'keep',
    // E1 (#407) — record replay lineage on the NEW row (soft reference).
    replayed_from_workspace_id: ws.workspace_id,
    ...(ws.name ? { workspace_name: ws.name } : {}),
    // E3 (#409) — replay-verbatim covers the recorded slots; omitted on
    // legacy rows (null) so their replay frame stays byte-identical.
    ...(ws.seed_overrides ? { seed_overrides: ws.seed_overrides } : {}),
    ...(ws.user_scope ? { user_scope: ws.user_scope } : {}),
    ...(runConfig
      ? { train_model_types: runConfig.trainModels, backtest: runConfig.backtest }
      : {}),
  }
}
