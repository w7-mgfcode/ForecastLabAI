// Pure builder for the ForecastOps action layer — turns a source model run
// into the POST /jobs body that retrains its (store, product) grain. Kept
// React-free and unit-tested (ops-actions.test.ts).
import type { JobCreate, ModelRun } from '@/types/api'

/** Read a numeric field from a run's model_config JSONB, or null when absent. */
function numericConfig(config: Record<string, unknown>, key: string): number | null {
  const value = config[key]
  return typeof value === 'number' ? value : null
}

/**
 * Build the `POST /jobs` body that retrains a grain from its source run.
 *
 * The train job consumes a FLAT params dict — verified against
 * `app/features/jobs/service.py::_execute_train`: `model_type`, `store_id`,
 * `product_id`, `start_date`, `end_date`, plus the model-specific
 * `season_length` (seasonal_naive) / `window_size` (moving_average) lifted
 * from the source run's `model_config`. There is no `period` key. The
 * end date is advanced to the freshest available sales date so the retrain
 * sees every observation since the original training window.
 *
 * @param run - The source model run (GET /registry/runs/{latest_run_id}).
 * @param latestSalesDate - summary.freshness.latest_sales_date, or null.
 */
export function buildRetrainJob(run: ModelRun, latestSalesDate: string | null): JobCreate {
  const params: Record<string, unknown> = {
    model_type: run.model_type,
    store_id: run.store_id,
    product_id: run.product_id,
    start_date: run.data_window_start,
    end_date: latestSalesDate ?? run.data_window_end,
  }
  const seasonLength = numericConfig(run.model_config, 'season_length')
  if (seasonLength !== null) {
    params.season_length = seasonLength
  }
  const windowSize = numericConfig(run.model_config, 'window_size')
  if (windowSize !== null) {
    params.window_size = windowSize
  }
  return { job_type: 'train', params }
}
