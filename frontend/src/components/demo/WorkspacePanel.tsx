/**
 * E4 (#393) — server-backed saved-workspaces panel for the Showcase page.
 *
 * Lists `showcase_workspace` rows (newest first) with three actions per row:
 * - Load   — re-attach: the page repopulates the run controls + renders the
 *            artifact deep-link cards. Read-only; no run starts.
 * - Replay — re-run: the page re-submits the recorded config verbatim through
 *            the existing WS run path with preservation="keep".
 * - Delete — remove the saved workspace METADATA row only (confirmed via
 *            dialog). The run's created objects — model runs, scenario plans,
 *            aliases, jobs, artifacts — are soft references and stay intact.
 *
 * The panel stays dumb: it hands the LIST item to the page callbacks; detail
 * fetching (created_objects) lives in the page via useWorkspace.
 */

import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { FolderOpen, Play, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useDeleteWorkspace, useWorkspaces } from '@/hooks/use-workspaces'
import { ApiError, getErrorMessage } from '@/lib/api'
import type { WorkspaceListItem } from '@/types/api'

interface WorkspacePanelProps {
  /** Called when the operator clicks Load — restore config + artifacts, no run. */
  onLoad: (ws: WorkspaceListItem) => void
  /** Called when the operator clicks Replay — re-run the recorded config. */
  onReplay: (ws: WorkspaceListItem) => void
  /** Called after a workspace row was deleted — lets the page drop a loaded one. */
  onDeleted?: (workspaceId: string) => void
  /** Disables all actions while a pipeline run is in flight. */
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

function labelOf(ws: WorkspaceListItem): string {
  return ws.name ?? ws.workspace_id.slice(0, 8)
}

export function WorkspacePanel({
  onLoad,
  onReplay,
  onDeleted,
  isRunning,
  lastWorkspaceId,
}: WorkspacePanelProps) {
  const { data, isLoading } = useWorkspaces()
  const queryClient = useQueryClient()
  const deleteWorkspace = useDeleteWorkspace()
  // The row awaiting confirmation — one shared dialog instead of one per row.
  const [pendingDelete, setPendingDelete] = useState<WorkspaceListItem | null>(null)

  const handleConfirmDelete = () => {
    const ws = pendingDelete
    if (!ws) return
    setPendingDelete(null)
    deleteWorkspace.mutate(ws.workspace_id, {
      onSuccess: () => {
        toast.success(
          `Workspace "${labelOf(ws)}" deleted — its model runs, scenarios, and artifacts were kept.`
        )
        onDeleted?.(ws.workspace_id)
      },
      onError: (error) => {
        toast.error(`Delete failed: ${getErrorMessage(error)}`)
        // A 404 means the row is already gone server-side — drop the stale entry.
        if (error instanceof ApiError && error.status === 404) {
          void queryClient.invalidateQueries({ queryKey: ['workspaces'] })
        }
      },
    })
  }

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
                  <span className="font-semibold">{labelOf(ws)}</span>
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
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-destructive"
                    disabled={isRunning || deleteWorkspace.isPending}
                    onClick={() => setPendingDelete(ws)}
                    aria-label={`Delete workspace ${labelOf(ws)}`}
                  >
                    <Trash2 className="mr-1 h-3 w-3" />
                    Delete
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>

      {/* Shared confirmation dialog for the row pending deletion. */}
      <AlertDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Delete workspace {pendingDelete ? `"${labelOf(pendingDelete)}"` : ''}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              This removes only the saved workspace record — its replay config
              and artifact links. The model runs, scenario plans, aliases, jobs,
              and artifacts the run created are NOT deleted and remain available
              elsewhere in the app. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep workspace</AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirmDelete} data-testid="workspace-delete-confirm">
              Delete workspace
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  )
}
