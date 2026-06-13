/**
 * E2 (#408) — replay confirmation dialog with a recorded-vs-sent preview.
 *
 * Every panel Replay goes through this dialog (no code path starts a replay
 * without it). The body renders a Field / Recorded / Will-send table; rows
 * where the two values differ are highlighted (defensive — a verbatim replay
 * normally matches). A reset=true workspace escalates: destructive warning
 * copy + a destructive-styled confirm button ("Replay & wipe database").
 *
 * Replay policy stays verbatim by design — operators who want a different
 * config use Load (which repopulates every control) and Run instead.
 */

import { AlertTriangle } from 'lucide-react'
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'
import type { DemoRunRequest, WorkspaceListItem } from '@/types/api'

interface ReplayConfirmDialogProps {
  /** The workspace pending replay — null keeps the dialog closed. */
  workspace: WorkspaceListItem | null
  /** The exact request the confirmed replay will send (single source). */
  requestPreview: DemoRunRequest | null
  onConfirm: () => void
  onCancel: () => void
}

function fmt(value: unknown): string {
  if (value === undefined || value === null || value === '') return '—'
  return String(value)
}

interface PreviewRow {
  field: string
  recorded: unknown
  willSend: unknown
}

function buildRows(ws: WorkspaceListItem, req: DemoRunRequest): PreviewRow[] {
  return [
    { field: 'seed', recorded: ws.seed, willSend: req.seed },
    { field: 'scenario', recorded: ws.scenario, willSend: req.scenario },
    { field: 'reset', recorded: ws.reset, willSend: req.reset },
    { field: 'skip_seed', recorded: ws.skip_seed, willSend: req.skip_seed },
    { field: 'name', recorded: ws.name, willSend: req.workspace_name ?? null },
    { field: 'preservation', recorded: 'keep', willSend: req.preservation },
    {
      field: 'replayed_from',
      recorded: ws.workspace_id,
      willSend: req.replayed_from_workspace_id,
    },
  ]
}

export function ReplayConfirmDialog({
  workspace,
  requestPreview,
  onConfirm,
  onCancel,
}: ReplayConfirmDialogProps) {
  const rows =
    workspace && requestPreview ? buildRows(workspace, requestPreview) : []
  const destructive = workspace?.reset === true
  const label = workspace?.name ?? workspace?.workspace_id.slice(0, 8) ?? ''

  return (
    <AlertDialog
      open={workspace !== null}
      onOpenChange={(open) => {
        if (!open) onCancel()
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Replay workspace “{label}”?</AlertDialogTitle>
          <AlertDialogDescription>
            The recorded config is re-submitted verbatim as a new kept run —
            the original workspace row is never changed.
          </AlertDialogDescription>
        </AlertDialogHeader>

        {destructive && (
          <div className="flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              Replaying this workspace <strong>WIPES the database</strong> and
              reseeds it from scratch.
            </span>
          </div>
        )}

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Field</TableHead>
              <TableHead>Recorded</TableHead>
              <TableHead>Will send</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => {
              const mismatch = fmt(row.recorded) !== fmt(row.willSend)
              return (
                <TableRow key={row.field}>
                  <TableCell className="font-medium">{row.field}</TableCell>
                  <TableCell className="font-mono text-xs">{fmt(row.recorded)}</TableCell>
                  <TableCell
                    className={cn(
                      'font-mono text-xs',
                      mismatch && 'font-semibold text-destructive'
                    )}
                  >
                    {fmt(row.willSend)}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>

        <p className="text-xs text-muted-foreground">
          Want to change the config first? Use Load instead.
        </p>

        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            data-testid="replay-confirm"
            onClick={onConfirm}
            className={cn(
              destructive &&
                'bg-destructive text-destructive-foreground hover:bg-destructive/90'
            )}
          >
            {destructive ? 'Replay & wipe database' : 'Replay'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
