/**
 * E4 (#393) / E2 (#408) — server-backed saved-workspaces panel for the
 * Showcase page.
 *
 * Lists `showcase_workspace` rows with lifecycle management (E2 #408):
 * - Toolbar: name search, show-archived toggle, allow-listed sort, active
 *   tag-filter chip. The panel owns the list params; filtering/sorting is
 *   server-side (pinned rows always order first).
 * - Per-row: Load (restore config, read-only), Replay (routes through the
 *   page's confirm dialog via onRequestReplay — NO replay starts here),
 *   pin toggle, actions dropdown (pin / archive / edit details / delete),
 *   pinned/archived/replay badges, clickable tag chips.
 * - Multi-select: per-row checkboxes; Delete selected (N sequential single
 *   DELETEs behind one confirmation — deliberately NO bulk endpoint) and
 *   Compare (exactly 2 → /showcase/compare?a=&b=).
 *
 * Deletes remove the workspace METADATA row only — created objects are soft
 * references and stay intact.
 */

import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  Archive,
  ArchiveRestore,
  FolderOpen,
  MoreHorizontal,
  Pencil,
  Pin,
  PinOff,
  Play,
  Search,
  Trash2,
  X,
} from 'lucide-react'
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
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useDeleteWorkspace, usePatchWorkspace, useWorkspaces } from '@/hooks/use-workspaces'
import { ApiError, getErrorMessage } from '@/lib/api'
import { ROUTES } from '@/lib/constants'
import { cn } from '@/lib/utils'
import type { WorkspaceListItem, WorkspaceListParams } from '@/types/api'
import { WorkspaceEditDialog } from './WorkspaceEditDialog'

interface WorkspacePanelProps {
  /** Called when the operator clicks Load — restore config + artifacts, no run. */
  onLoad: (ws: WorkspaceListItem) => void
  /**
   * E2 (#408) — called when the operator clicks Replay. The PAGE owns the
   * confirmation dialog; the panel never starts a replay itself.
   */
  onRequestReplay: (ws: WorkspaceListItem) => void
  /** Called after a workspace row was deleted — lets the page drop a loaded one. */
  onDeleted?: (workspaceId: string) => void
  /** Disables all actions while a pipeline run is in flight. */
  isRunning: boolean
  /** summary.workspaceId of the latest kept run — triggers a list refetch. */
  lastWorkspaceId: string | null
}

type SortKey = 'newest' | 'oldest' | 'name' | 'status'

const SORT_PARAMS: Record<SortKey, Pick<WorkspaceListParams, 'sort_by' | 'sort_order'>> = {
  newest: {},
  oldest: { sort_by: 'created_at', sort_order: 'asc' },
  name: { sort_by: 'name', sort_order: 'asc' },
  status: { sort_by: 'status', sort_order: 'asc' },
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
  onRequestReplay,
  onDeleted,
  isRunning,
  lastWorkspaceId,
}: WorkspacePanelProps) {
  // ── E2 (#408) — server-side list params ─────────────────────────────────
  const [search, setSearch] = useState('')
  const [appliedQ, setAppliedQ] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('newest')
  const [tagFilter, setTagFilter] = useState<string | null>(null)

  // Debounced search — the q param needs >= 2 chars (server min_length).
  useEffect(() => {
    const handle = window.setTimeout(() => setAppliedQ(search.trim()), 300)
    return () => window.clearTimeout(handle)
  }, [search])

  const params = useMemo<WorkspaceListParams>(
    () => ({
      ...(appliedQ.length >= 2 ? { q: appliedQ } : {}),
      ...(tagFilter ? { tags: tagFilter } : {}),
      ...(showArchived ? { include_archived: true } : {}),
      ...SORT_PARAMS[sortKey],
    }),
    [appliedQ, tagFilter, showArchived, sortKey]
  )

  const { data, isLoading } = useWorkspaces(params)
  const queryClient = useQueryClient()
  const deleteWorkspace = useDeleteWorkspace()
  const patchWorkspace = usePatchWorkspace()

  // ── dialogs + selection state ────────────────────────────────────────────
  const [pendingDelete, setPendingDelete] = useState<WorkspaceListItem | null>(null)
  const [pendingEdit, setPendingEdit] = useState<WorkspaceListItem | null>(null)
  const [confirmMultiDelete, setConfirmMultiDelete] = useState(false)
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set())
  const navigate = useNavigate()

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

  // E2 (#408) — multi-select delete: N sequential SINGLE deletes (no bulk
  // endpoint by design); failures collect into one summary toast.
  const handleConfirmDeleteSelected = async () => {
    const ids = Array.from(selected)
    setConfirmMultiDelete(false)
    const failures: string[] = []
    for (const id of ids) {
      try {
        await deleteWorkspace.mutateAsync(id)
        onDeleted?.(id)
      } catch (error) {
        failures.push(`${id.slice(0, 8)}: ${getErrorMessage(error)}`)
      }
    }
    setSelected(new Set())
    if (failures.length === 0) {
      toast.success(
        `Deleted ${ids.length} workspace record${ids.length === 1 ? '' : 's'} — created objects were kept.`
      )
    } else {
      toast.error(`Some deletes failed: ${failures.join('; ')}`)
    }
  }

  const handleTogglePin = (ws: WorkspaceListItem) => {
    patchWorkspace.mutate(
      { workspaceId: ws.workspace_id, update: { pinned: !ws.pinned } },
      { onError: (error) => toast.error(`Update failed: ${getErrorMessage(error)}`) }
    )
  }

  const handleToggleArchive = (ws: WorkspaceListItem) => {
    patchWorkspace.mutate(
      { workspaceId: ws.workspace_id, update: { archived: !ws.archived } },
      {
        onSuccess: () => {
          toast.success(ws.archived ? 'Workspace unarchived.' : 'Workspace archived.')
        },
        onError: (error) => toast.error(`Update failed: ${getErrorMessage(error)}`),
      }
    )
  }

  const toggleSelected = (workspaceId: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(workspaceId)) next.delete(workspaceId)
      else next.add(workspaceId)
      return next
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
  const allSelected = items.length > 0 && items.every((ws) => selected.has(ws.workspace_id))
  const selectedIds = Array.from(selected)
  const hasActiveFilter = appliedQ.length >= 2 || tagFilter !== null || showArchived

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

        {/* E2 (#408) — toolbar: search / show-archived / sort / tag chip. */}
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
            <Input
              className="h-8 w-44 pl-7 text-xs"
              placeholder="Search by name…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="Search workspaces by name"
            />
          </div>
          <label className="flex items-center gap-2">
            <Checkbox
              checked={showArchived}
              onCheckedChange={(v) => setShowArchived(v === true)}
            />
            <span>Show archived</span>
          </label>
          <Select value={sortKey} onValueChange={(v) => setSortKey(v as SortKey)}>
            <SelectTrigger className="h-8 w-32 text-xs" aria-label="Sort workspaces">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="newest">Newest</SelectItem>
              <SelectItem value="oldest">Oldest</SelectItem>
              <SelectItem value="name">Name</SelectItem>
              <SelectItem value="status">Status</SelectItem>
            </SelectContent>
          </Select>
          {tagFilter && (
            <Badge variant="secondary" className="gap-1">
              tag: {tagFilter}
              <button
                type="button"
                aria-label={`Clear tag filter ${tagFilter}`}
                onClick={() => setTagFilter(null)}
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          )}
        </div>

        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {isLoading
              ? 'Loading workspaces…'
              : hasActiveFilter
                ? 'No workspaces match the active filters.'
                : 'No saved workspaces yet — tick "Save as workspace" before a run to keep it.'}
          </p>
        ) : (
          <>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <Checkbox
                checked={allSelected}
                onCheckedChange={(v) =>
                  setSelected(
                    v === true ? new Set(items.map((ws) => ws.workspace_id)) : new Set()
                  )
                }
                aria-label="Select all workspaces"
              />
              <span>Select all</span>
            </label>
            <ul className="space-y-2">
              {items.map((ws) => (
                <li
                  key={ws.workspace_id}
                  className={cn(
                    'flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2 text-xs',
                    ws.archived && 'opacity-60'
                  )}
                >
                  <div className="flex flex-wrap items-center gap-3 font-mono">
                    <Checkbox
                      checked={selected.has(ws.workspace_id)}
                      onCheckedChange={() => toggleSelected(ws.workspace_id)}
                      aria-label={`Select workspace ${labelOf(ws)}`}
                    />
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-6 w-6 p-0"
                      disabled={isRunning || patchWorkspace.isPending}
                      onClick={() => handleTogglePin(ws)}
                      aria-label={ws.pinned ? `Unpin ${labelOf(ws)}` : `Pin ${labelOf(ws)}`}
                    >
                      {ws.pinned ? (
                        <Pin className="h-3 w-3 fill-current" />
                      ) : (
                        <PinOff className="h-3 w-3 text-muted-foreground" />
                      )}
                    </Button>
                    <span className="font-semibold">{labelOf(ws)}</span>
                    {ws.archived && <Badge variant="outline">archived</Badge>}
                    {ws.replayed_from_workspace_id && <Badge variant="outline">replay</Badge>}
                    <span className="rounded bg-muted px-2 py-0.5">{ws.scenario}</span>
                    <span>seed {ws.seed}</span>
                    <span className={statusClass(ws.status)}>{ws.status.toUpperCase()}</span>
                    {winnerOf(ws) && <span>winner {winnerOf(ws)}</span>}
                    {ws.reset && (
                      <span className="text-destructive">
                        DESTRUCTIVE (replay wipes all data)
                      </span>
                    )}
                    {ws.tags.map((tag) => (
                      <button
                        key={tag}
                        type="button"
                        onClick={() => setTagFilter(tag)}
                        aria-label={`Filter by tag ${tag}`}
                      >
                        <Badge variant="secondary">{tag}</Badge>
                      </button>
                    ))}
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
                      onClick={() => onRequestReplay(ws)}
                    >
                      <Play className="mr-1 h-3 w-3" />
                      Replay
                    </Button>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={isRunning}
                          aria-label={`More actions for ${labelOf(ws)}`}
                        >
                          <MoreHorizontal className="h-3 w-3" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => handleTogglePin(ws)}>
                          {ws.pinned ? (
                            <PinOff className="mr-2 h-3 w-3" />
                          ) : (
                            <Pin className="mr-2 h-3 w-3" />
                          )}
                          {ws.pinned ? 'Unpin' : 'Pin'}
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => handleToggleArchive(ws)}>
                          {ws.archived ? (
                            <ArchiveRestore className="mr-2 h-3 w-3" />
                          ) : (
                            <Archive className="mr-2 h-3 w-3" />
                          )}
                          {ws.archived ? 'Unarchive' : 'Archive'}
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => setPendingEdit(ws)}>
                          <Pencil className="mr-2 h-3 w-3" />
                          Edit details…
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          className="text-destructive"
                          onClick={() => setPendingDelete(ws)}
                        >
                          <Trash2 className="mr-2 h-3 w-3" />
                          Delete…
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </li>
              ))}
            </ul>

            {/* E2 (#408) — selection footer. */}
            {selectedIds.length > 0 && (
              <div className="flex flex-wrap items-center gap-3 rounded-md border bg-muted/50 px-3 py-2 text-xs">
                <span className="font-medium">{selectedIds.length} selected</span>
                <Button
                  size="sm"
                  variant="outline"
                  className="text-destructive"
                  disabled={isRunning || deleteWorkspace.isPending}
                  onClick={() => setConfirmMultiDelete(true)}
                >
                  <Trash2 className="mr-1 h-3 w-3" />
                  Delete selected ({selectedIds.length})
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={selectedIds.length !== 2}
                  title={
                    selectedIds.length !== 2 ? 'Select exactly two workspaces to compare' : undefined
                  }
                  onClick={() =>
                    navigate(
                      `${ROUTES.SHOWCASE_COMPARE}?a=${selectedIds[0]}&b=${selectedIds[1]}`
                    )
                  }
                >
                  Compare
                </Button>
              </div>
            )}
          </>
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

      {/* E2 (#408) — one confirmation for the whole selection. */}
      <AlertDialog
        open={confirmMultiDelete}
        onOpenChange={(open) => {
          if (!open) setConfirmMultiDelete(false)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {selectedIds.length} workspace records?</AlertDialogTitle>
            <AlertDialogDescription>
              Their created objects are NOT deleted — model runs, scenario
              plans, aliases, jobs, and artifacts stay available elsewhere in
              the app. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep workspaces</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => void handleConfirmDeleteSelected()}
              data-testid="workspace-multi-delete-confirm"
            >
              Delete selected
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* E2 (#408) — rename / notes / tags editor. */}
      <WorkspaceEditDialog workspace={pendingEdit} onClose={() => setPendingEdit(null)} />
    </Card>
  )
}
