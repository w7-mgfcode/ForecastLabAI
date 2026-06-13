/**
 * E5 (#411) — render the agent/HITL + RAG story captured on a LOADED
 * workspace row. Three sections:
 *   - Approval history: each approval_events entry (decision badge + tool +
 *     transcript snippet + when).
 *   - Knowledge events: each rag_events entry (event/status/provider/count).
 *   - Reproduction markers: result_summary.story_reproduction chips (replay
 *     rows only — rendered only when present).
 *
 * Renders NOTHING for legacy rows that carry neither slot nor a reproduction
 * marker. Reads the row only — the run is long gone, the row is the memory
 * (same contract as WorkspaceArtifactsPanel).
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { StatusBadge } from '@/components/common/status-badge'
import type {
  ApprovalEventDetail,
  RagEventDetail,
  WorkspaceDetail,
} from '@/types/api'

interface WorkspaceStoryPanelProps {
  workspace: WorkspaceDetail
}

/** Format an ISO timestamp for display; '—' when null. */
function formatWhen(value: string | null | undefined): string {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

/** Decision → StatusBadge variant. */
function decisionVariant(
  decision: string | null,
): 'success' | 'error' | 'warning' | 'default' {
  if (decision === 'approved') return 'success'
  if (decision === 'rejected') return 'error'
  if (decision === 'timed_out') return 'warning'
  return 'default'
}

/** rag_events status → StatusBadge variant. */
function ragStatusVariant(status: string): 'success' | 'warning' | 'pending' | 'default' {
  if (status === 'pass') return 'success'
  if (status === 'warn') return 'warning'
  if (status === 'skip') return 'pending'
  return 'default'
}

/** story_reproduction verdict → StatusBadge variant. */
function verdictVariant(verdict: string): 'success' | 'error' | 'pending' | 'default' {
  if (verdict === 'reproduced') return 'success'
  if (verdict === 'not_reproduced') return 'error'
  if (verdict === 'not_applicable' || verdict === 'unknown') return 'pending'
  return 'default'
}

/** Read result_summary.story_reproduction as a tolerant map of string verdicts. */
function readReproduction(
  summary: Record<string, unknown> | null,
): Record<string, string> | null {
  if (!summary || typeof summary !== 'object') return null
  const raw = (summary as Record<string, unknown>).story_reproduction
  if (!raw || typeof raw !== 'object') return null
  const out: Record<string, string> = {}
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof value === 'string') out[key] = value
  }
  return Object.keys(out).length > 0 ? out : null
}

export function WorkspaceStoryPanel({ workspace }: WorkspaceStoryPanelProps) {
  const approvalEvents: ApprovalEventDetail[] = workspace.approval_events ?? []
  const ragEvents: RagEventDetail[] = workspace.rag_events ?? []
  const reproduction = readReproduction(workspace.result_summary)

  // Legacy rows: nothing captured -> render nothing.
  if (approvalEvents.length === 0 && ragEvents.length === 0 && reproduction === null) {
    return null
  }

  return (
    <Card data-testid="workspace-story-panel">
      <CardHeader>
        <CardTitle>Run story</CardTitle>
        <CardDescription>
          The agent/HITL approval and knowledge moments this run captured —
          replayed from the workspace row.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Reproduction markers — replay rows only. */}
        {reproduction && (
          <div className="space-y-2" data-testid="story-reproduction">
            <h3 className="text-sm font-semibold">Replay reproduction</h3>
            <div className="flex flex-wrap items-center gap-2">
              {Object.entries(reproduction)
                .filter(([key]) => key !== 'source_workspace_id')
                .map(([key, verdict]) => (
                  <span key={key} className="flex items-center gap-1.5 text-xs">
                    <span className="text-muted-foreground">{key}</span>
                    <StatusBadge variant={verdictVariant(verdict)}>
                      {verdict.replace(/_/g, ' ')}
                    </StatusBadge>
                  </span>
                ))}
            </div>
          </div>
        )}

        {/* Approval history. */}
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">Approval history</h3>
          {approvalEvents.length === 0 ? (
            <p className="text-sm text-muted-foreground">No approval events recorded.</p>
          ) : (
            <ul className="space-y-2">
              {approvalEvents.map((event, index) => (
                <li
                  key={`${event.action_id ?? 'action'}-${index}`}
                  className="rounded-md border p-3"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge variant={decisionVariant(event.decision)}>
                      {event.decision ?? 'unknown'}
                    </StatusBadge>
                    {event.tool_name && (
                      <span className="font-mono text-xs text-muted-foreground">
                        {event.tool_name}
                      </span>
                    )}
                    {event.auto_approved === true && (
                      <span className="text-xs text-muted-foreground">(auto)</span>
                    )}
                    <span className="ml-auto text-xs text-muted-foreground">
                      {formatWhen(event.decided_at)}
                    </span>
                  </div>
                  {event.transcript_summary && (
                    <p className="mt-1 break-words text-sm text-muted-foreground">
                      {event.transcript_summary}
                    </p>
                  )}
                  {event.reason && (
                    <p className="mt-1 text-xs text-muted-foreground">
                      reason: {event.reason}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Knowledge events. */}
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">Knowledge events</h3>
          {ragEvents.length === 0 ? (
            <p className="text-sm text-muted-foreground">No knowledge events recorded.</p>
          ) : (
            <ul className="space-y-2">
              {ragEvents.map((event, index) => (
                <li
                  key={`${event.event}-${index}`}
                  className="flex flex-wrap items-center gap-2 rounded-md border p-3 text-xs"
                >
                  <span className="font-mono font-semibold">{event.event}</span>
                  <StatusBadge variant={ragStatusVariant(event.status)}>
                    {event.status}
                  </StatusBadge>
                  {event.provider && (
                    <span className="rounded-md bg-muted px-2 py-0.5 font-mono">
                      {event.provider}
                    </span>
                  )}
                  <span className="text-muted-foreground">count: {event.count}</span>
                  {event.detail && (
                    <span className="break-words text-muted-foreground">{event.detail}</span>
                  )}
                  <span className="ml-auto text-muted-foreground">
                    {formatWhen(event.occurred_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
