/**
 * E4 (#393) — server-backed saved-workspaces panel for the Showcase page.
 *
 * Lists `showcase_workspace` rows (newest first) with two actions per row:
 * - Load   — re-attach: the page repopulates the run controls + renders the
 *            artifact deep-link cards. Read-only; no run starts.
 * - Replay — re-run: the page re-submits the recorded config verbatim through
 *            the existing WS run path with preservation="keep".
 *
 * The panel stays dumb: it hands the LIST item to the page callbacks; detail
 * fetching (created_objects) lives in the page via useWorkspace.
 */

import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { FolderOpen, Play } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useWorkspaces } from '@/hooks/use-workspaces'
import type { WorkspaceListItem } from '@/types/api'

interface WorkspacePanelProps {
  /** Called when the operator clicks Load — restore config + artifacts, no run. */
  onLoad: (ws: WorkspaceListItem) => void
  /** Called when the operator clicks Replay — re-run the recorded config. */
  onReplay: (ws: WorkspaceListItem) => void
  /** Disables both actions while a pipeline run is in flight. */
  isRunning: boolean
  /** summary.workspaceId of the latest kept run — triggers a list refetch. */
  lastWorkspaceId: string | null
}

function statusClass(status: WorkspaceListItem['status']): string {
  switch (status) {
    case 'completed':
      return 'text-success font-semibold'
    case 'failed':
      return 'text-destructive font-semibold'
    default:
      return 'text-muted-foreground font-semibold'
  }
}

function winnerOf(ws: WorkspaceListItem): string | null {
  const winner = ws.result_summary?.winner_model_type
  return typeof winner === 'string' ? winner : null
}

export function WorkspacePanel({ onLoad, onReplay, isRunning, lastWorkspaceId }: WorkspacePanelProps) {
  const { data, isLoading } = useWorkspaces()
  const queryClient = useQueryClient()

  // Refetch the list once the latest kept run settles — syncing React state to
  // an external system (the server-backed list) is the sanctioned effect use.
  useEffect(() => {
    if (lastWorkspaceId) {
      void queryClient.invalidateQueries({ queryKey: ['workspaces'] })
    }
  }, [lastWorkspaceId, queryClient])

  const items = data?.workspaces ?? []

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">Saved workspaces</h2>
          {data && data.total > items.length && (
            <span className="text-xs text-muted-foreground">
              showing {items.length} of {data.total}
            </span>
          )}
        </div>
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {isLoading
              ? 'Loading workspaces…'
              : 'No saved workspaces yet — tick "Save as workspace" before a run to keep it.'}
          </p>
        ) : (
          <ul className="space-y-2">
            {items.map((ws) => (
              <li
                key={ws.workspace_id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2 text-xs"
              >
                <div className="flex flex-wrap items-center gap-3 font-mono">
                  <span className="font-semibold">{ws.name ?? ws.workspace_id.slice(0, 8)}</span>
                  <span className="rounded bg-muted px-2 py-0.5">{ws.scenario}</span>
                  <span>seed {ws.seed}</span>
                  <span className={statusClass(ws.status)}>{ws.status.toUpperCase()}</span>
                  {winnerOf(ws) && <span>winner {winnerOf(ws)}</span>}
                  {ws.reset && (
                    <span className="text-destructive">
                      DESTRUCTIVE (replay wipes all data)
                    </span>
                  )}
                  <span className="text-muted-foreground">
                    {new Date(ws.created_at).toLocaleString()}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={isRunning}
                    onClick={() => onLoad(ws)}
                  >
                    <FolderOpen className="mr-1 h-3 w-3" />
                    Load
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={isRunning}
                    onClick={() => onReplay(ws)}
                  >
                    <Play className="mr-1 h-3 w-3" />
                    Replay
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
