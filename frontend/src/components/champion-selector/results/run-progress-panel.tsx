import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { StatusBadge } from '@/components/common/status-badge'
import { getStatusVariant } from '@/lib/status-utils'
import type {
  CandidateProgress,
  ModelSelectionStatus,
  SelectionProgress,
} from '@/types/api'

interface RunProgressPanelProps {
  status: ModelSelectionStatus
  progress: SelectionProgress | null
  candidates: CandidateProgress[]
}

function Count({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border bg-muted/30 px-3 py-2 text-center">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-lg font-semibold tabular-nums">{value}</p>
    </div>
  )
}

/**
 * Live async-run progress (Slice B): the run status, per-status counts, and a
 * per-candidate table. Failed/cancelled candidates stay visible.
 */
export function RunProgressPanel({ status, progress, candidates }: RunProgressPanelProps) {
  return (
    <Card data-testid="run-progress-panel">
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-lg">Comparison progress</CardTitle>
          <StatusBadge variant={getStatusVariant(status)} data-testid="run-status-badge">
            {status}
          </StatusBadge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {progress && (
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
            <Count label="Total" value={progress.total} />
            <Count label="Pending" value={progress.pending} />
            <Count label="Running" value={progress.running} />
            <Count label="Completed" value={progress.completed} />
            <Count label="Failed" value={progress.failed} />
            <Count label="Cancelled" value={progress.cancelled} />
          </div>
        )}
        {candidates.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground">
                <th className="py-1.5">Model</th>
                <th className="py-1.5">Status</th>
                <th className="py-1.5 text-right">Duration</th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((c) => (
                <tr
                  key={c.candidate_id}
                  data-testid={`candidate-row-${c.model_type}`}
                  className="border-t"
                >
                  <td className="py-1.5 font-medium">{c.model_type}</td>
                  <td className="py-1.5">
                    <StatusBadge variant={getStatusVariant(c.status)}>
                      {c.status}
                    </StatusBadge>
                    {c.error && (
                      <span className="ml-2 text-xs text-destructive">{c.error}</span>
                    )}
                  </td>
                  <td className="py-1.5 text-right tabular-nums text-muted-foreground">
                    {c.duration_ms === null ? '—' : `${(c.duration_ms / 1000).toFixed(1)}s`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  )
}
