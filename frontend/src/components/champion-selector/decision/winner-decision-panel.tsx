import { useState } from 'react'
import { Loader2, Trophy, TriangleAlert } from 'lucide-react'
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
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { TrainWinnerResponse } from '@/types/api'

interface WinnerDecisionPanelProps {
  winnerModelType: string
  /** Every candidate offered in the run (winner + runners-up + failed). */
  candidateModelTypes: string[]
  isTraining: boolean
  trainResult: TrainWinnerResponse | null
  /** Train the chosen model — the page routes winner vs. override. */
  onTrain: (modelType: string, overrideReason: string | null) => void
}

/**
 * Slice C — accept the recommended winner OR override to another candidate.
 *
 * Picking a non-winner opens a confirm dialog (explicit warning + an optional
 * reason) before training. Presentational — the page owns the train mutations.
 */
export function WinnerDecisionPanel({
  winnerModelType,
  candidateModelTypes,
  isTraining,
  trainResult,
  onTrain,
}: WinnerDecisionPanelProps) {
  const [selected, setSelected] = useState(winnerModelType)
  const [overrideReason, setOverrideReason] = useState('')
  const [confirmOpen, setConfirmOpen] = useState(false)

  const isOverride = selected !== winnerModelType

  function handleTrainClick() {
    if (isOverride) {
      setConfirmOpen(true)
      return
    }
    onTrain(selected, null)
  }

  function handleConfirmOverride() {
    onTrain(selected, overrideReason.trim() || null)
    setConfirmOpen(false)
  }

  return (
    <Card data-testid="winner-decision-panel">
      <CardHeader>
        <CardTitle>5 · Decide &amp; train</CardTitle>
        <CardDescription>
          Train the recommended champion, or override to another candidate. The
          recommended model is <span className="font-medium">{winnerModelType}</span>.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="space-y-1">
            <span className="text-xs text-muted-foreground">Model to train</span>
            <Select value={selected} onValueChange={setSelected}>
              <SelectTrigger className="w-64" data-testid="decision-model-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {candidateModelTypes.map((mt) => (
                  <SelectItem key={mt} value={mt}>
                    {mt}
                    {mt === winnerModelType ? ' (recommended)' : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button
            type="button"
            onClick={handleTrainClick}
            disabled={isTraining}
            data-testid="decision-train-button"
          >
            {isTraining ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Trophy className="mr-2 h-4 w-4" />
            )}
            {isOverride ? 'Train override' : 'Train recommended'}
          </Button>
        </div>

        {trainResult?.override_warning && (
          <div
            className="flex items-start gap-2 rounded-md border border-warning/40 bg-warning/10 p-2 text-xs"
            data-testid="decision-override-warning"
          >
            <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
            <span>{trainResult.override_warning}</span>
          </div>
        )}

        {trainResult && !trainResult.override_warning && (
          <p className="text-xs text-muted-foreground" data-testid="decision-trained-note">
            Trained <span className="font-medium">{trainResult.model_type}</span>.
          </p>
        )}
      </CardContent>

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent data-testid="override-confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Train a non-recommended model?</AlertDialogTitle>
            <AlertDialogDescription>
              You picked <span className="font-medium">{selected}</span> instead of the
              recommended <span className="font-medium">{winnerModelType}</span>. This is an
              override and is recorded on the run.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-1">
            <span className="text-xs text-muted-foreground">Reason (optional)</span>
            <Input
              value={overrideReason}
              onChange={(event) => setOverrideReason(event.target.value)}
              placeholder="e.g. domain seasonality outweighs the WAPE lead"
              data-testid="override-reason-input"
            />
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmOverride}
              data-testid="override-confirm-action"
            >
              Train override
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  )
}
