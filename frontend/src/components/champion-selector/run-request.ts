import type {
  ModelSelectionRunRequest,
  RankingMetric,
  SplitConfig,
} from '@/types/api'

export interface AssembleRunRequestInput {
  storeId: number
  productId: number
  startDate: string // YYYY-MM-DD
  endDate: string // YYYY-MM-DD
  forecastHorizon: number
  rankingMetric: RankingMetric
  splitConfig: SplitConfig
  selectedModels: string[]
}

/**
 * Assemble the typed `ModelSelectionRunRequest` from the Champion Selector
 * form state. Pure + side-effect-free so it can be unit-tested.
 *
 * Slice A pins `auto_train_winner` and `auto_predict` to `false`: the async run
 * path (Slice B) treats both as NO-OPS, and Slice C owns explicit
 * train/predict. `split_config.horizon` is forced equal to `forecast_horizon`
 * (the backend `ModelSelectionRunRequest` validator requires it). The request
 * is assembled but NOT sent in Slice A — the "Run comparison" CTA is disabled.
 */
export function assembleRunRequest(
  input: AssembleRunRequestInput,
): ModelSelectionRunRequest {
  return {
    store_id: input.storeId,
    product_id: input.productId,
    selection_window: {
      start_date: input.startDate,
      end_date: input.endDate,
    },
    forecast_horizon: input.forecastHorizon,
    ranking_metric: input.rankingMetric,
    split_config: { ...input.splitConfig, horizon: input.forecastHorizon },
    candidate_models: input.selectedModels.map((model_type) => ({
      model_type,
      params: {},
    })),
    feature_frame_version: 1,
    feature_groups: null,
    auto_train_winner: false,
    auto_predict: false,
  }
}
