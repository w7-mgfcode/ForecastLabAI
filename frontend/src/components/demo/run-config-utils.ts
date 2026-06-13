import type {
  DemoBacktestConfig,
  DemoRankingMetric,
  ModelFamily,
  ScenarioPreset,
} from '@/types/api'

/**
 * E4 (#410) — pure helpers for the showcase run-config panel. Kept in a `.ts`
 * module (not a `.tsx`) so the `react-refresh/only-export-components` lint rule
 * stays happy and the logic is unit-testable without rendering.
 */

// The legacy demo trio — the default selection (and the byte-compat baseline).
export const DEFAULT_TRAIN_MODELS = ['naive', 'seasonal_naive', 'moving_average']

// The legacy demo split + ranking metric. Mirrors the backend defaults
// (DEMO_HORIZON=14, DEMO_BACKTEST_SPLITS=3, DEMO_MIN_TRAIN_SIZE=30, gap=0,
// strategy 'expanding', metric 'wape').
export const DEFAULT_BACKTEST: DemoBacktestConfig = {
  horizon: 14,
  strategy: 'expanding',
  n_splits: 3,
  min_train_size: 30,
  gap: 0,
  metric: 'wape',
}

// The V2 feature-aware model appended to a custom selection on showcase_rich
// (the v2_train step trains/registers it unconditionally; see pipeline.py).
export const SHOWCASE_V2_MODEL = 'prophet_like'

/** True when `models` equals the default trio (order-insensitive). */
export function isDefaultSelection(models: string[]): boolean {
  if (models.length !== DEFAULT_TRAIN_MODELS.length) return false
  const a = [...models].sort()
  const b = [...DEFAULT_TRAIN_MODELS].sort()
  return a.every((m, i) => m === b[i])
}

/** True when every backtest knob equals its default. */
export function isDefaultBacktest(cfg: DemoBacktestConfig): boolean {
  return (
    cfg.horizon === DEFAULT_BACKTEST.horizon &&
    cfg.strategy === DEFAULT_BACKTEST.strategy &&
    cfg.n_splits === DEFAULT_BACKTEST.n_splits &&
    cfg.min_train_size === DEFAULT_BACKTEST.min_train_size &&
    cfg.gap === DEFAULT_BACKTEST.gap &&
    cfg.metric === DEFAULT_BACKTEST.metric
  )
}

export interface TrainPlanEntry {
  model_type: string
  family?: ModelFamily
  /** Appended V2 entry (prophet_like on showcase_rich) — not operator-picked. */
  v2?: boolean
}

/**
 * The exact models the pipeline will train, in display order. On showcase_rich
 * `prophet_like (V2)` is appended (unless already selected) because the
 * v2_train step registers it unconditionally — it stays in the competition.
 * The `families` map (model_type → family, from the catalog) tags each chip.
 */
export function buildTrainPlan(
  models: string[],
  scenario: ScenarioPreset,
  families: Record<string, ModelFamily> = {},
): TrainPlanEntry[] {
  const plan: TrainPlanEntry[] = models.map((m) => ({
    model_type: m,
    family: families[m],
  }))
  if (scenario === 'showcase_rich' && !models.includes(SHOWCASE_V2_MODEL)) {
    plan.push({ model_type: SHOWCASE_V2_MODEL, family: families[SHOWCASE_V2_MODEL], v2: true })
  }
  return plan
}

/**
 * The seeded window (days) for a scenario. SOURCE OF TRUTH:
 * pipeline.py `_SCENARIO_SEED_PROFILE` (demo_minimal / sparse / holiday_rush =
 * 92-day window, every other preset = 180). Keep in sync.
 */
export function windowDaysFor(scenario: ScenarioPreset): number {
  if (scenario === 'demo_minimal' || scenario === 'sparse' || scenario === 'holiday_rush') {
    return 92
  }
  return 180
}

/**
 * A soft (non-blocking) warning when the split cannot fit the seeded window:
 * `min_train_size + n_splits * (horizon + gap) > windowDays`. The backend does
 * NOT clamp — an over-aggressive split fails honestly at backtest (sparse-preset
 * precedent), so the UI warns ahead of time. Returns null when the split fits.
 */
export function splitFitWarning(
  cfg: DemoBacktestConfig,
  scenario: ScenarioPreset,
): string | null {
  const windowDays = windowDaysFor(scenario)
  const required = cfg.min_train_size + cfg.n_splits * (cfg.horizon + cfg.gap)
  if (required > windowDays) {
    return (
      `This split needs ~${required} days but ${scenario} seeds ~${windowDays}. ` +
      'The backtest may produce NaN / too-few-folds and fail — reduce horizon, splits, or min train.'
    )
  }
  return null
}

/**
 * Parse a stored `run_config` (Record<string, unknown> from a workspace row)
 * into the typed pieces Load/Replay repopulate. Returns null when absent or
 * shapeless. Missing knobs fall back to the defaults so a partial stored config
 * still yields a complete backtest object.
 */
export function parseRunConfig(
  raw: Record<string, unknown> | null | undefined,
): { trainModels: string[]; backtest: DemoBacktestConfig } | null {
  if (!raw || typeof raw !== 'object') return null
  const rawModels = (raw as { train_model_types?: unknown }).train_model_types
  const trainModels =
    Array.isArray(rawModels) && rawModels.every((m) => typeof m === 'string')
      ? (rawModels as string[])
      : DEFAULT_TRAIN_MODELS
  const rawBacktest = (raw as { backtest?: unknown }).backtest
  const backtest = parseBacktest(rawBacktest)
  return { trainModels, backtest }
}

function parseBacktest(raw: unknown): DemoBacktestConfig {
  if (!raw || typeof raw !== 'object') return { ...DEFAULT_BACKTEST }
  const obj = raw as Record<string, unknown>
  const num = (key: keyof DemoBacktestConfig, fallback: number): number =>
    typeof obj[key] === 'number' ? (obj[key] as number) : fallback
  const strategy = obj.strategy === 'sliding' ? 'sliding' : DEFAULT_BACKTEST.strategy
  const metricRaw = obj.metric
  const metric: DemoRankingMetric =
    metricRaw === 'mae' || metricRaw === 'rmse' || metricRaw === 'wape'
      ? metricRaw
      : DEFAULT_BACKTEST.metric
  return {
    horizon: num('horizon', DEFAULT_BACKTEST.horizon),
    strategy,
    n_splits: num('n_splits', DEFAULT_BACKTEST.n_splits),
    min_train_size: num('min_train_size', DEFAULT_BACKTEST.min_train_size),
    gap: num('gap', DEFAULT_BACKTEST.gap),
    metric,
  }
}
