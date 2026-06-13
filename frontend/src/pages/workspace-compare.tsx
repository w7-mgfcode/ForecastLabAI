/**
 * E2 (#408) — two-workspace compare page (/showcase/compare?a=&b=).
 *
 * Mirrors the run-compare two-picker pattern (pages/explorer/run-compare.tsx)
 * but the diff is FRONTEND-ONLY: a workspace compare is a plain field diff
 * over two already-served WorkspaceDetail payloads — no backend endpoint.
 * Renders: config table (mismatches highlighted), result-summary diff
 * (WAPE delta is sign-only), created-objects presence matrix, lineage note
 * when one side replays the other, and partial-run badges. Invalid/missing
 * ids degrade to the picker — never a crash.
 */

import { Link, useSearchParams } from 'react-router-dom'
import { ArrowDown, ArrowLeft, ArrowUp } from 'lucide-react'
import { useWorkspace, useWorkspaces } from '@/hooks/use-workspaces'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatNumber } from '@/lib/api'
import { ROUTES } from '@/lib/constants'
import { cn } from '@/lib/utils'
import type { WorkspaceDetail, WorkspaceListItem } from '@/types/api'

/** Neutral delta indicator — sign only, no better/worse colour-coding. */
function DeltaCell({ diff }: { diff: number | null }) {
  if (diff == null) {
    return <span className="text-muted-foreground">—</span>
  }
  if (diff > 0) {
    return (
      <span className="inline-flex items-center gap-1">
        <ArrowUp className="h-3 w-3" />
        {formatNumber(diff, 4)}
      </span>
    )
  }
  if (diff < 0) {
    return (
      <span className="inline-flex items-center gap-1">
        <ArrowDown className="h-3 w-3" />
        {formatNumber(diff, 4)}
      </span>
    )
  }
  return <span>{formatNumber(diff, 4)}</span>
}

function labelOf(ws: WorkspaceListItem): string {
  return ws.name ?? ws.workspace_id.slice(0, 8)
}

function WorkspacePicker({
  label,
  value,
  workspaces,
  onSelect,
}: {
  label: string
  value: string
  workspaces: WorkspaceListItem[]
  onSelect: (workspaceId: string) => void
}) {
  return (
    <div className="space-y-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <Select value={value || undefined} onValueChange={onSelect}>
        <SelectTrigger className="w-full">
          <SelectValue placeholder="Select a workspace…" />
        </SelectTrigger>
        <SelectContent>
          {workspaces.map((ws) => (
            <SelectItem key={ws.workspace_id} value={ws.workspace_id}>
              {labelOf(ws)} · {ws.scenario} · {ws.status}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

function summaryNumber(ws: WorkspaceDetail, key: string): number | null {
  const value = ws.result_summary?.[key]
  return typeof value === 'number' ? value : null
}

function summaryString(ws: WorkspaceDetail, key: string): string | null {
  const value = ws.result_summary?.[key]
  return typeof value === 'string' ? value : null
}

interface ConfigRow {
  field: string
  a: string
  b: string
}

function buildConfigRows(a: WorkspaceDetail, b: WorkspaceDetail): ConfigRow[] {
  const fmt = (value: unknown): string =>
    value === null || value === undefined || value === '' ? '—' : String(value)
  return [
    { field: 'seed', a: fmt(a.seed), b: fmt(b.seed) },
    { field: 'scenario', a: fmt(a.scenario), b: fmt(b.scenario) },
    { field: 'reset', a: fmt(a.reset), b: fmt(b.reset) },
    { field: 'skip_seed', a: fmt(a.skip_seed), b: fmt(b.skip_seed) },
    { field: 'name', a: fmt(a.name), b: fmt(b.name) },
    { field: 'tags', a: fmt(a.tags.join(', ')), b: fmt(b.tags.join(', ')) },
  ]
}

/** Union of soft-reference keys recorded on either side. */
function objectKeys(a: WorkspaceDetail, b: WorkspaceDetail): string[] {
  return Array.from(
    new Set([...Object.keys(a.created_objects), ...Object.keys(b.created_objects)])
  ).sort()
}

function lineageNote(a: WorkspaceDetail, b: WorkspaceDetail): string | null {
  if (b.replayed_from_workspace_id === a.workspace_id) {
    return 'Workspace B is a replay of workspace A.'
  }
  if (a.replayed_from_workspace_id === b.workspace_id) {
    return 'Workspace A is a replay of workspace B.'
  }
  return null
}

function SideStatus({ ws }: { ws: WorkspaceDetail }) {
  return (
    <span className="inline-flex items-center gap-2">
      {ws.status}
      {ws.status !== 'completed' && (
        <Badge variant="outline" className="text-destructive">
          partial run
        </Badge>
      )}
    </span>
  )
}

export default function WorkspaceComparePage() {
  const [params, setParams] = useSearchParams()
  const a = params.get('a') ?? ''
  const b = params.get('b') ?? ''

  // Pickers include archived rows — comparing an archived run is legitimate.
  const listQuery = useWorkspaces({ limit: 100, include_archived: true })
  const detailA = useWorkspace(a, !!a)
  const detailB = useWorkspace(b, !!b)

  function selectWorkspace(slot: 'a' | 'b', workspaceId: string) {
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set(slot, workspaceId)
      return next
    })
  }

  const workspaces = listQuery.data?.workspaces ?? []
  const wsA = detailA.data
  const wsB = detailB.data
  // A 404 (deleted id in the URL) degrades to the picker — never a crash.
  const bothReady = !!wsA && !!wsB

  const wapeA = wsA ? summaryNumber(wsA, 'winner_wape') : null
  const wapeB = wsB ? summaryNumber(wsB, 'winner_wape') : null
  const note = bothReady ? lineageNote(wsA, wsB) : null

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <Button asChild variant="ghost" size="sm" className="-ml-2 h-7">
          <Link to={ROUTES.SHOWCASE}>
            <ArrowLeft className="mr-1 h-4 w-4" />
            Back to Showcase
          </Link>
        </Button>
        <h1 className="text-3xl font-bold">Compare workspaces</h1>
        <p className="text-sm text-muted-foreground">
          Pick two saved showcase workspaces to compare their replay config,
          results, and recorded objects side by side.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Select workspaces</CardTitle>
          <CardDescription>
            The comparison is deep-linkable — the URL carries the two workspace ids.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <WorkspacePicker
            label="Workspace A"
            value={a}
            workspaces={workspaces}
            onSelect={(id) => selectWorkspace('a', id)}
          />
          <WorkspacePicker
            label="Workspace B"
            value={b}
            workspaces={workspaces}
            onSelect={(id) => selectWorkspace('b', id)}
          />
        </CardContent>
      </Card>

      {(!a || !b || detailA.error || detailB.error || !bothReady) && (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            {detailA.error || detailB.error
              ? 'One of the selected workspaces no longer exists — select another above.'
              : detailA.isLoading || detailB.isLoading
                ? 'Loading workspaces…'
                : 'Select two workspaces above to see the comparison.'}
          </CardContent>
        </Card>
      )}

      {bothReady && (
        <>
          {note && (
            <Card>
              <CardContent className="py-4 text-sm" data-testid="lineage-note">
                {note}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Config</CardTitle>
              <CardDescription>
                Recorded replay config — mismatching rows are highlighted.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Field</TableHead>
                    <TableHead>Workspace A</TableHead>
                    <TableHead>Workspace B</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableRow>
                    <TableCell className="font-medium">Workspace ID</TableCell>
                    <TableCell className="break-all font-mono text-xs">
                      {wsA.workspace_id}
                    </TableCell>
                    <TableCell className="break-all font-mono text-xs">
                      {wsB.workspace_id}
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="font-medium">Status</TableCell>
                    <TableCell>
                      <SideStatus ws={wsA} />
                    </TableCell>
                    <TableCell>
                      <SideStatus ws={wsB} />
                    </TableCell>
                  </TableRow>
                  {buildConfigRows(wsA, wsB).map((row) => {
                    const mismatch = row.a !== row.b
                    return (
                      <TableRow key={row.field}>
                        <TableCell className="font-medium">{row.field}</TableCell>
                        <TableCell className={cn('text-xs', mismatch && 'font-semibold')}>
                          {row.a}
                        </TableCell>
                        <TableCell className={cn('text-xs', mismatch && 'font-semibold')}>
                          {row.b}
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Results</CardTitle>
              <CardDescription>
                Δ is Workspace B minus Workspace A — sign only, not a quality judgement.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Metric</TableHead>
                    <TableHead>Workspace A</TableHead>
                    <TableHead>Workspace B</TableHead>
                    <TableHead>Δ</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableRow>
                    <TableCell className="font-medium">Winner</TableCell>
                    <TableCell>{summaryString(wsA, 'winner_model_type') ?? '—'}</TableCell>
                    <TableCell>{summaryString(wsB, 'winner_model_type') ?? '—'}</TableCell>
                    <TableCell>
                      <span className="text-muted-foreground">—</span>
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="font-medium">Winner WAPE</TableCell>
                    <TableCell>{wapeA != null ? formatNumber(wapeA, 4) : '—'}</TableCell>
                    <TableCell>{wapeB != null ? formatNumber(wapeB, 4) : '—'}</TableCell>
                    <TableCell>
                      <DeltaCell
                        diff={wapeA != null && wapeB != null ? wapeB - wapeA : null}
                      />
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="font-medium">Wall-clock (s)</TableCell>
                    <TableCell>
                      {summaryNumber(wsA, 'wall_clock_s') != null
                        ? formatNumber(summaryNumber(wsA, 'wall_clock_s')!, 1)
                        : '—'}
                    </TableCell>
                    <TableCell>
                      {summaryNumber(wsB, 'wall_clock_s') != null
                        ? formatNumber(summaryNumber(wsB, 'wall_clock_s')!, 1)
                        : '—'}
                    </TableCell>
                    <TableCell>
                      <span className="text-muted-foreground">—</span>
                    </TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Created objects</CardTitle>
              <CardDescription>
                Which soft references each run recorded (✓ recorded / — absent).
              </CardDescription>
            </CardHeader>
            <CardContent>
              {objectKeys(wsA, wsB).length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Neither workspace recorded any created objects.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Object</TableHead>
                      <TableHead>Workspace A</TableHead>
                      <TableHead>Workspace B</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {objectKeys(wsA, wsB).map((key) => (
                      <TableRow key={key}>
                        <TableCell className="font-mono text-xs">{key}</TableCell>
                        <TableCell>{key in wsA.created_objects ? '✓' : '—'}</TableCell>
                        <TableCell>{key in wsB.created_objects ? '✓' : '—'}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
