/**
 * E2 (#408) — replay lineage breadcrumb for the loaded workspace.
 *
 * Renders the replayed_from_workspace_id chain newest → original:
 * `this ← parent ← grandparent …` (depth-capped). Ancestors are clickable
 * (loads them); a deleted ancestor renders as "(original deleted)" — dangling
 * soft references are designed, never an error. Renders nothing when the
 * loaded workspace is not a replay.
 */

import { Fragment } from 'react'
import { Button } from '@/components/ui/button'
import { useWorkspaceLineage } from '@/hooks/use-workspaces'
import type { WorkspaceDetail } from '@/types/api'

interface WorkspaceLineageStripProps {
  workspaceId: string
  /** Load an ancestor into the page (full detail — the walk already has it). */
  onLoadAncestor: (ws: WorkspaceDetail) => void
}

function labelOf(workspaceId: string, name: string | null): string {
  return name ?? workspaceId.slice(0, 8)
}

export function WorkspaceLineageStrip({ workspaceId, onLoadAncestor }: WorkspaceLineageStripProps) {
  const { data } = useWorkspaceLineage(workspaceId)
  const entries = data?.entries ?? []

  // No lineage to show: still walking, or the loaded row is not a replay.
  if (entries.length < 2) return null

  return (
    <div
      className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground"
      data-testid="workspace-lineage"
    >
      <span className="font-medium">Replay lineage:</span>
      {entries.map((entry, index) => (
        <Fragment key={`${entry.workspace_id}-${index}`}>
          {index > 0 && <span aria-hidden>←</span>}
          {entry.deleted ? (
            <span className="italic">(original deleted)</span>
          ) : index === 0 ? (
            // The loaded workspace itself — not a link.
            <span className="font-mono font-semibold text-foreground">
              {labelOf(entry.workspace_id, entry.name)}
            </span>
          ) : (
            <Button
              variant="link"
              size="sm"
              className="h-auto p-0 font-mono text-xs"
              onClick={() => entry.detail && onLoadAncestor(entry.detail)}
            >
              {labelOf(entry.workspace_id, entry.name)}
            </Button>
          )}
        </Fragment>
      ))}
      {data?.truncated && <span aria-hidden>…</span>}
    </div>
  )
}
