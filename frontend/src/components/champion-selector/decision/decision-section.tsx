import { useMemo, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { getErrorMessage } from '@/lib/api'
import {
  usePredictWinner,
  usePromoteChampion,
  useTrainSelected,
  useTrainWinner,
} from '@/hooks/use-model-selection'
import type {
  ModelCatalogResponse,
  ModelSelectionRunResponse,
  PredictWinnerResponse,
  TrainWinnerResponse,
} from '@/types/api'
import { WinnerDecisionPanel } from './winner-decision-panel'
import { TrainForecastActions } from './train-forecast-actions'
import { ForecastSummaryCard } from './forecast-summary-card'
import { ForecastChart } from './forecast-chart'
import { DailyForecastTable } from './daily-forecast-table'
import { BusinessInterpretationPanel } from './business-interpretation-panel'
import { SafetyStockPanel } from './safety-stock-panel'
import { PromoteChampionDialog } from './promote-champion-dialog'

interface DecisionSectionProps {
  selectionId: string
  run: ModelSelectionRunResponse
  catalog: ModelCatalogResponse | undefined
}

/**
 * Slice C — the decision section rendered below a terminal winning run.
 *
 * Owns the train / predict / promote mutations (so the page keeps its hooks
 * unconditional). Mount it with `key={selectionId}` so a fresh run resets the
 * train/forecast/promote state.
 */
export function DecisionSection({ selectionId, run, catalog }: DecisionSectionProps) {
  const winnerModelType = run.winner?.model_type ?? null

  const [trainResult, setTrainResult] = useState<TrainWinnerResponse | null>(null)
  const [predictResult, setPredictResult] = useState<PredictWinnerResponse | null>(null)
  const [leadTimeDays, setLeadTimeDays] = useState(7)
  const [serviceLevel, setServiceLevel] = useState(0.95)
  const [promoteOpen, setPromoteOpen] = useState(false)
  const [promoteError, setPromoteError] = useState<string | null>(null)
  const [promotedAlias, setPromotedAlias] = useState<string | null>(null)

  const trainWinner = useTrainWinner(selectionId)
  const trainSelected = useTrainSelected(selectionId)
  const predict = usePredictWinner(selectionId)
  const promote = usePromoteChampion(selectionId)

  // Every candidate the run offered (winner + runners-up + failed), de-duped.
  const candidateModelTypes = useMemo(() => {
    const seen = new Set<string>()
    for (const entry of run.ranking) seen.add(entry.model_type)
    if (winnerModelType) seen.add(winnerModelType)
    return [...seen]
  }, [run.ranking, winnerModelType])

  // Capability of the model that WILL be (or was) trained — drives the blocked
  // forecast state for a feature-aware winner (LOCKED #5).
  const activeModelType = trainResult?.model_type ?? winnerModelType
  const supportsAutoPredict = useMemo(() => {
    const info = catalog?.models.find((m) => m.model_type === activeModelType)
    return info?.supports_auto_predict ?? true
  }, [catalog, activeModelType])

  const trained = trainResult !== null || run.final_model !== null

  if (winnerModelType === null) return null

  function handleTrain(modelType: string, overrideReason: string | null) {
    setPredictResult(null)
    setPromotedAlias(null)
    const onSuccess = (data: TrainWinnerResponse) => setTrainResult(data)
    if (modelType === winnerModelType) {
      trainWinner.mutate(undefined, { onSuccess })
    } else {
      trainSelected.mutate({ model_type: modelType, override_reason: overrideReason }, { onSuccess })
    }
  }

  function handleForecast() {
    predict.mutate(
      { lead_time_days: leadTimeDays, service_level: serviceLevel },
      { onSuccess: (data) => setPredictResult(data) },
    )
  }

  function handlePromote(body: Parameters<typeof promote.mutate>[0]) {
    setPromoteError(null)
    promote.mutate(body, {
      onSuccess: (data) => setPromotedAlias(data.alias_name),
      onError: (err) => setPromoteError(getErrorMessage(err)),
    })
  }

  const forecast = predictResult?.forecast ?? null
  const decision = predictResult?.decision ?? null
  const isOverride = trainResult?.is_override ?? false

  return (
    <div className="space-y-6" data-testid="decision-section">
      <WinnerDecisionPanel
        winnerModelType={winnerModelType}
        candidateModelTypes={candidateModelTypes}
        isTraining={trainWinner.isPending || trainSelected.isPending}
        trainResult={trainResult}
        onTrain={handleTrain}
      />

      <Card>
        <CardContent className="flex flex-col gap-4 pt-6">
          <TrainForecastActions
            supportsAutoPredict={supportsAutoPredict}
            trained={trained}
            isPredicting={predict.isPending}
            onForecast={handleForecast}
          />
          {predict.isError && (
            <p className="text-sm text-destructive" data-testid="forecast-error">
              {getErrorMessage(predict.error)}
            </p>
          )}
        </CardContent>
      </Card>

      {forecast && (
        <>
          <ForecastSummaryCard forecast={forecast} />
          <ForecastChart forecast={forecast} />
          <DailyForecastTable forecast={forecast} />
          <BusinessInterpretationPanel
            businessSummary={run.business_summary}
            decision={decision}
          />
          <SafetyStockPanel
            decision={decision}
            leadTimeDays={leadTimeDays}
            serviceLevel={serviceLevel}
            isRecomputing={predict.isPending}
            onLeadTimeChange={setLeadTimeDays}
            onServiceLevelChange={setServiceLevel}
            onRecompute={handleForecast}
          />
        </>
      )}

      {trained && (
        <Card>
          <CardContent className="flex items-center justify-between gap-3 pt-6">
            <p className="text-sm text-muted-foreground">
              Promote the trained champion to a registry alias (approval-gated).
            </p>
            <Button
              type="button"
              onClick={() => setPromoteOpen(true)}
              data-testid="open-promote-dialog"
            >
              Promote champion
            </Button>
          </CardContent>
        </Card>
      )}

      <PromoteChampionDialog
        open={promoteOpen}
        onOpenChange={setPromoteOpen}
        isOverride={isOverride}
        isPromoting={promote.isPending}
        promoteError={promoteError}
        promotedAlias={promotedAlias}
        onConfirm={handlePromote}
      />
    </div>
  )
}
