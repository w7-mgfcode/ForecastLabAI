// === Pagination ===
export interface PaginatedResponse<T> {
  total: number
  page: number
  page_size: number
  items?: T[]
}

// === Dimensions ===
export interface Store {
  id: number
  code: string
  name: string
  region: string | null
  city: string | null
  store_type: string | null
  created_at: string
  updated_at: string
}

export interface StoreListResponse extends PaginatedResponse<Store> {
  stores: Store[]
}

export interface Product {
  id: number
  sku: string
  name: string
  category: string | null
  brand: string | null
  base_price: string | null
  base_cost: string | null
  created_at: string
  updated_at: string
}

export interface ProductListResponse extends PaginatedResponse<Product> {
  products: Product[]
}

// === Analytics ===
export interface KPIMetrics {
  total_revenue: string
  total_units: number
  total_transactions: number
  avg_unit_price: string | null
  avg_basket_value: string | null
}

export interface KPIResponse {
  metrics: KPIMetrics
  start_date: string
  end_date: string
  store_id: number | null
  product_id: number | null
  category: string | null
}

export interface DrilldownItem {
  dimension_value: string
  dimension_id: number | null
  metrics: KPIMetrics
  rank: number
  revenue_share_pct: string
}

export type DrilldownDimension = 'store' | 'product' | 'category' | 'region' | 'date'

export interface DrilldownResponse {
  dimension: DrilldownDimension
  items: DrilldownItem[]
  total_items: number
  start_date: string
  end_date: string
  store_id: number | null
  product_id: number | null
}

// Bucket size for GET /analytics/timeseries.
export type TimeGranularity = 'day' | 'week' | 'month' | 'quarter'

// One aggregated period of the sales time series.
export interface TimeSeriesPoint {
  period: string // ISO date (bucket start)
  metrics: KPIMetrics
}

// Response from GET /analytics/timeseries (points ascending by period).
export interface TimeSeriesResponse {
  granularity: TimeGranularity
  points: TimeSeriesPoint[]
  total_points: number
  start_date: string
  end_date: string
  store_id: number | null
  product_id: number | null
  category: string | null
}

// One forecast point from a completed `predict` job's result.forecasts array.
// lower_bound / upper_bound are present only for models that emit intervals.
export interface ForecastPoint {
  date: string // ISO date
  forecast: number
  lower_bound?: number | null
  upper_bound?: number | null
}

// One item of GET /analytics/inventory-status — the latest inventory snapshot
// for one (store, product) grain.
export interface InventoryStatusItem {
  store_id: number
  product_id: number
  date: string // ISO date (latest snapshot)
  on_hand_qty: number
  on_order_qty: number
  is_stockout: boolean
}

// Response from GET /analytics/inventory-status (one item per grain).
export interface InventoryStatusResponse {
  items: InventoryStatusItem[]
  total_items: number
  store_id: number | null
  product_id: number | null
}

// Client-derived view-model row for the Demand Planner table (camelCase — NOT
// a wire contract). One per completed `predict` job. `onHand`/`onOrder`/
// `inventoryRequirement` are null when no inventory snapshot exists for the grain.
export interface DemandRow {
  jobId: string
  runId: string | null
  storeId: number
  productId: number
  sku: string
  productName: string
  modelType: string
  horizon: number
  tomorrow: number
  nextWeek: number
  nextMonth: number
  nextMonthPartial: boolean
  onHand: number | null
  onOrder: number | null
  isStockout: boolean
  inventoryRequirement: number | null
  forecasts: ForecastPoint[]
}

// One day of a product's lifecycle demand curve.
export interface LifecyclePoint {
  date: string // ISO date
  stage: string
  multiplier: number
}

// Response from GET /dimensions/products/{id}/lifecycle-curve.
export interface LifecycleCurveResponse {
  product_id: number
  sku: string
  launch_date: string | null
  discontinue_date: string | null
  start_date: string
  end_date: string
  points: LifecyclePoint[]
  total: number
}

// === Registry ===
export type RunStatus = 'pending' | 'running' | 'success' | 'failed' | 'archived'

// MLZOO-D / PRP-31: derived from model_type on the backend as a Pydantic
// computed_field (no DB column, no migration). Surfaced on every ModelRun
// response so the runs explorer, run detail, run compare, and forecast viz
// pages can render a consistent Family badge.
export type ModelFamily = 'baseline' | 'tree' | 'additive'

// PRP-37 Slice C — Forecast Intelligence A (PRP-35).
// Mirrors `app/shared/feature_frames/contract_v2.py:FeatureGroup`. Lowercase
// wire form is canonical; the StrEnum on the backend matches these values.
export type FeatureFrameVersion = 1 | 2

export type FeatureGroup =
  | 'target_history'
  | 'rolling'
  | 'trend'
  | 'calendar'
  | 'price_promo'
  | 'inventory'
  | 'lifecycle'
  | 'replenishment'
  | 'returns'
  | 'exogenous_weather'
  | 'exogenous_macro'

export const FEATURE_GROUP_VALUES = [
  'target_history',
  'rolling',
  'trend',
  'calendar',
  'price_promo',
  'inventory',
  'lifecycle',
  'replenishment',
  'returns',
  'exogenous_weather',
  'exogenous_macro',
] as const satisfies readonly FeatureGroup[]

export type FeatureSafetyClass =
  | 'safe'
  | 'conditionally_safe'
  | 'unsafe_unless_supplied'

export interface ModelRun {
  run_id: string
  status: RunStatus
  model_type: string
  model_family: ModelFamily
  model_config: Record<string, unknown>
  feature_config: Record<string, unknown> | null
  config_hash: string
  data_window_start: string
  data_window_end: string
  store_id: number
  product_id: number
  metrics: Record<string, number> | null
  artifact_uri: string | null
  artifact_hash: string | null
  artifact_size_bytes: number | null
  runtime_info: Record<string, unknown> | null
  agent_context: Record<string, unknown> | null
  git_sha: string | null
  error_message: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
  /** PRP-36 computed_field — `null` for legacy / V1 runs. */
  feature_frame_version?: FeatureFrameVersion | null
  /** PRP-36 computed_field — per-group feature lists, `null` for V1 runs. */
  feature_groups?: Partial<Record<FeatureGroup, string[]>> | null
}

// MLZOO-D / PRP-31: response shape for the two feature-metadata endpoints
// (/forecasting/runs/{run_id}/feature-metadata and the jobs/{job_id} sibling).
// When sourced from a job, `run_id` is the **artifact key** (12-char hex)
// parsed from the bundle file name, NOT a registry UUID.
export interface FeatureImportanceItem {
  name: string
  importance: number  // signed for kind='linear_coef' (prophet_like ridge coef)
  kind: 'tree' | 'linear_coef'
  rank: number  // 1-indexed by |importance| descending
}

export interface FeatureMetadataResponse {
  run_id: string
  model_type: string
  model_family: ModelFamily
  feature_columns: string[]
  features: FeatureImportanceItem[]
  importance_type: string | null
  /** PRP-35 — present on every response; defaults to 1 server-side. */
  feature_frame_version?: FeatureFrameVersion
  /** PRP-35 — per-group feature lists; V1 returns null. */
  feature_groups?: Partial<Record<FeatureGroup, string[]>> | null
  /** PRP-35 — column → safety class map; V1 returns null. */
  feature_safety_classes?: Record<string, FeatureSafetyClass> | null
}

export interface RunListResponse extends PaginatedResponse<ModelRun> {
  runs: ModelRun[]
}

export interface Alias {
  alias_name: string
  run_id: string
  run_status: RunStatus
  model_type: string
  description: string | null
  created_at: string
  updated_at: string
}

export interface RunCompareResponse {
  run_a: ModelRun
  run_b: ModelRun
  config_diff: Record<string, unknown>
  metrics_diff: Record<string, { a: number | null; b: number | null; diff: number | null }>
}

// Response from GET /registry/runs/{run_id}/verify (SHA-256 integrity check).
// On a checksum mismatch the endpoint returns HTTP 200 with verified:false + error.
export interface ArtifactVerifyResponse {
  verified: boolean
  run_id: string
  artifact_uri: string
  stored_hash?: string
  computed_hash?: string
  error?: string
}

// === Backtesting (PRP-36) ===
//
// `aggregated_metrics` is a flat `dict[str, float]` on the wire (NOT a Pydantic
// class) — RMSE rides inside it under the key `"rmse"`. Per-horizon-bucket
// metrics use the same dict-of-dict shape.

export interface FoldResult {
  fold: number
  /** PRP-36 — per-bucket metrics; empty when no horizon-bucket split fired. */
  horizon_bucket_metrics?: Record<string, Record<string, number>>
  [key: string]: unknown
}

export interface ModelBacktestResult {
  model_type: string
  aggregated_metrics: Record<string, number>
  fold_results: FoldResult[]
  /** PRP-36 — per-bucket aggregates across folds; null when no fold emitted a bucket dict. */
  bucketed_aggregated_metrics?: Record<string, Record<string, number>> | null
  [key: string]: unknown
}

export interface BacktestResponse {
  main_model_results: ModelBacktestResult
  baseline_results?: ModelBacktestResult[]
  comparison_summary?: Record<string, unknown> | null
  [key: string]: unknown
}

// === Jobs ===
export type JobType = 'train' | 'predict' | 'backtest'
export type JobStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface Job {
  job_id: string
  job_type: JobType
  status: JobStatus
  params: Record<string, unknown>
  result: Record<string, unknown> | null
  error_message: string | null
  error_type: string | null
  run_id: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
}

export interface JobListResponse extends PaginatedResponse<Job> {
  jobs: Job[]
}

export interface JobCreate {
  job_type: JobType
  params: Record<string, unknown>
}

// === Batch (PRP-33) ===

export type BatchOperation =
  | 'train'
  | 'predict'
  | 'backtest'
  | 'train_backtest_register'

export type BatchStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'partial'
  | 'cancelled'

// Terminal parent statuses — mirrors ``TERMINAL_BATCH_STATES`` derived from
// the backend ``VALID_BATCH_TRANSITIONS`` state machine. Any UI that needs
// to gate on "this batch is settled" reads from here so the API and UI
// definitions cannot drift.
export const TERMINAL_BATCH_STATES: ReadonlySet<BatchStatus> = new Set([
  'completed',
  'failed',
  'partial',
  'cancelled',
])

export type BatchItemStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'

export type BatchScopeKind =
  | 'manual'
  | 'region'
  | 'category'
  | 'top_revenue'
  | 'all'

export interface BatchScope {
  kind: BatchScopeKind
  store_ids?: number[] | null
  product_ids?: number[] | null
  region?: string | null
  category?: string | null
  top_n?: number | null
}

// PRP-37 Slice C — Forecast-train control inputs. `feature_frame_version` +
// `feature_groups` MUST be omitted (undefined) when V1 is selected — the
// backend rejects `feature_groups` on a V1 train.
export interface TrainRequest {
  store_id: number
  product_id: number
  start_date: string
  end_date: string
  model_type: string
  config?: Record<string, unknown>
  /** PRP-35 — defaults to 1 server-side; omit to keep that default. */
  feature_frame_version?: FeatureFrameVersion
  /** PRP-35 — V2 only; rejected by the backend when version=1. */
  feature_groups?: FeatureGroup[]
}

export interface BatchModelConfig {
  // PRP-36 expanded the model zoo (weighted_moving_average,
  // seasonal_average, trend_regression_baseline, random_forest). Kept as a
  // literal union so a typo at call-site is caught at compile time.
  model_type:
    | 'naive'
    | 'seasonal_naive'
    | 'moving_average'
    | 'weighted_moving_average'
    | 'seasonal_average'
    | 'trend_regression_baseline'
    | 'regression'
    | 'lightgbm'
    | 'xgboost'
    | 'random_forest'
    | 'prophet_like'
  params?: Record<string, unknown>
  /** PRP-37 — propagated into the per-item train; V1 default when omitted. */
  feature_frame_version?: FeatureFrameVersion
  /** PRP-37 — only valid when feature_frame_version=2. */
  feature_groups?: FeatureGroup[]
}

export interface BatchSubmitRequest {
  operation: BatchOperation
  scope: BatchScope
  model_configs: BatchModelConfig[]
  start_date: string
  end_date: string
  max_parallel?: number
  default_child_priority?: number
}

export interface BatchSubmitResponse {
  batch_id: string
  operation: BatchOperation
  status: BatchStatus
  total_items: number
  completed_items: number
  failed_items: number
  running_items: number
  cancelled_items: number
  max_parallel: number
  // PRP-34: resolved server-side from
  // result_summary.effective_max_parallel — 0 for legacy pre-PRP-34 rows.
  effective_max_parallel: number
  started_at: string | null
  completed_at: string | null
  result_summary: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface BatchItemResponse {
  item_id: string
  batch_id: string
  store_id: number
  product_id: number
  model_type: string
  status: BatchItemStatus
  priority: number
  metrics: Record<string, number | null> | null
  child_job_id: string | null
  child_run_id: string | null
  error_message: string | null
  error_type: string | null
  started_at: string | null
  completed_at: string | null
  duration_ms: number | null
  created_at: string
  updated_at: string
}

export interface BatchItemListResponse {
  items: BatchItemResponse[]
  total: number
  page: number
  page_size: number
}

// === RAG ===
export interface RagSource {
  source_id: string
  source_type: string
  source_path: string
  chunk_count: number
  content_hash: string
  indexed_at: string
  metadata: Record<string, unknown> | null
}

export interface SourceListResponse {
  sources: RagSource[]
  total_sources: number
  total_chunks: number
}

export interface IndexDocumentRequest {
  source_type: string
  source_path: string
  content?: string
}

export interface IndexDocumentResponse {
  source_id: string
  chunks_created: number
}

// Semantic-search request for POST /rag/retrieve.
// Mirrors app/features/rag/schemas.py RetrieveRequest (extra="forbid" — send
// nothing beyond these fields). Omit similarity_threshold to use the server default.
export interface RetrieveRequest {
  query: string
  top_k?: number // 1..50, server default 5
  similarity_threshold?: number // 0..1
  filters?: Record<string, unknown> | null
}

// One matching chunk from a semantic search.
export interface ChunkResult {
  chunk_id: string
  source_id: string
  source_path: string
  source_type: string
  content: string
  relevance_score: number // 0..1
  metadata: Record<string, unknown> | null
}

// Response from POST /rag/retrieve.
export interface RetrieveResponse {
  results: ChunkResult[]
  query_embedding_time_ms: number
  search_time_ms: number
  total_chunks_searched: number
}

// Request for POST /rag/index/project-docs. All flags default to true
// server-side (extra="forbid"), so the UI posts an empty {}.
export interface IndexProjectDocsRequest {
  include_docs?: boolean
  include_prps?: boolean
  include_root?: boolean
}

// One file's outcome in a project-docs index run.
export interface ProjectDocResult {
  source_path: string
  status: 'indexed' | 'updated' | 'unchanged' | 'failed'
  chunks_created: number
  error: string | null
}

// Aggregate result of POST /rag/index/project-docs.
export interface IndexProjectDocsResponse {
  results: ProjectDocResult[]
  total_files: number
  indexed: number
  updated: number
  unchanged: number
  failed: number
  total_chunks: number
  duration_ms: number
}

// === Agents WebSocket ===
export type AgentEventType =
  | 'text_delta'
  | 'tool_call_start'
  | 'tool_call_end'
  | 'approval_required'
  | 'complete'
  | 'error'

export interface AgentStreamEvent {
  event_type: AgentEventType
  data: Record<string, unknown>
  timestamp: string
}

export type AgentType = 'experiment' | 'rag_assistant'

export interface AgentSession {
  session_id: string
  agent_type: AgentType
  status: 'active' | 'awaiting_approval' | 'expired' | 'closed'
  total_tokens_used: number
  tool_calls_count: number
  created_at: string
  expires_at: string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  tool_calls?: ToolCall[]
  citations?: Citation[]
  timestamp: string
}

/** Response from POST /agents/sessions/{id}/approve (mirrors backend ApprovalResponse). */
export interface ApprovalResponse {
  action_id: string
  approved: boolean
  /** Execution result on success, or `{ error, error_type }` when execution failed. */
  result?: unknown
  status: 'executed' | 'rejected' | 'expired'
}

export interface ToolCall {
  tool_name: string
  arguments: Record<string, unknown>
  result?: unknown
  status: 'pending' | 'running' | 'completed' | 'failed'
}

export interface Citation {
  source_type: string
  source_path: string
  chunk_id: string
  snippet: string
  relevance_score: number
}

// === Error Response (RFC 7807) ===
export interface ProblemDetail {
  type: string
  title: string
  status: number
  detail: string
  instance?: string
  errors?: Array<{ field: string; message: string; type: string }>
  code?: string
  request_id?: string
}

// === Seeder ===
export interface SeederStatus {
  stores: number
  products: number
  calendar: number
  sales: number
  inventory: number
  price_history: number
  promotions: number
  date_range_start: string | null // ISO date "2024-01-01"
  date_range_end: string | null
  last_updated: string | null // ISO datetime
}

export interface ScenarioInfo {
  name: string
  description: string
  stores: number
  products: number
  start_date: string // ISO date
  end_date: string
}

export interface GenerateParams {
  scenario?: string // default: "retail_standard"
  seed?: number // default: 42
  stores?: number // 1-100, default: 10
  products?: number // 1-500, default: 50
  start_date?: string // ISO date
  end_date?: string
  sparsity?: number // 0.0-1.0
  dry_run?: boolean
}

export interface AppendParams {
  start_date: string // Required
  end_date: string // Required
  seed?: number
}

export interface DeleteParams {
  scope?: 'all' | 'facts' | 'dimensions' // default: "all"
  dry_run?: boolean
}

export interface GenerateResult {
  success: boolean
  records_created: Record<string, number>
  duration_seconds: number
  message: string
  seed: number
}

export interface DeleteResult {
  success: boolean
  records_deleted: Record<string, number>
  message: string
  dry_run: boolean
}

export type VerifyCheckStatus = 'passed' | 'warning' | 'failed'

export interface VerifyCheck {
  name: string
  status: VerifyCheckStatus
  message: string
  details: string[] | null
}

export interface VerifyResult {
  passed: boolean
  checks: VerifyCheck[]
  total_checks: number
  passed_count: number
  warning_count: number
  failed_count: number
}

// === Demo Showcase ===
export type DemoStepStatus = 'running' | 'pass' | 'fail' | 'skip' | 'warn'
export type DemoEventType = 'step_start' | 'step_complete' | 'pipeline_complete' | 'error'

// PRP-38 / E2 (#391) — seeder scenario presets the picker offers. Mirrors
// the backend app/shared/seeder/config.py:ScenarioPreset enum's string
// values — all 8 members.
export type ScenarioPreset =
  | 'retail_standard'
  | 'holiday_rush'
  | 'high_variance'
  | 'stockout_heavy'
  | 'new_launches'
  | 'sparse'
  | 'demo_minimal'
  | 'showcase_rich'

// One streamed pipeline event from WS /demo/stream (matches the backend
// StepEvent Pydantic model; snake_case on the wire).
export interface StepEvent {
  event_type: DemoEventType
  step_name: string
  step_index: number
  total_steps: number
  status: DemoStepStatus | null
  detail: string
  duration_ms: number
  data: Record<string, unknown>
  timestamp: string
  // PRP-38 — additive phase grouping; Optional + Nullable for back-compat
  // with legacy demo_minimal clients that don't see phase fields.
  phase_name?: string | null
  phase_index?: number | null
  phase_total?: number | null
}

// Start frame for WS /demo/stream and request body for POST /demo/run.
export interface DemoRunRequest {
  seed?: number
  reset?: boolean
  skip_seed?: boolean
  // PRP-38 — optional scenario picker; default is 'demo_minimal' (back-compat).
  scenario?: ScenarioPreset
}

// Aggregate result returned by the synchronous POST /demo/run.
export interface DemoRunResult {
  overall_status: 'pass' | 'fail'
  steps: StepEvent[]
  winner_model_type: string | null
  winner_wape: number | null
  winning_run_id: string | null
  alias: string | null
  wall_clock_s: number
}

// === AI Model Configuration (/config) ===

// Presence + masked preview of one provider API key (never the raw value).
export interface ApiKeyStatus {
  provider: string
  is_set: boolean
  masked: string | null
}

// Effective AI-model configuration — GET /config/ai response.
export interface AIModelConfig {
  agent_default_model: string
  agent_fallback_model: string
  agent_temperature: number
  agent_max_tokens: number
  agent_thinking_budget: number | null
  agent_max_tool_calls: number
  agent_timeout_seconds: number
  agent_retry_attempts: number
  agent_session_ttl_minutes: number
  agent_require_approval: string[]
  rag_embedding_provider: string
  rag_embedding_model: string
  rag_embedding_dimension: number
  ollama_base_url: string
  ollama_embedding_model: string
  api_keys: ApiKeyStatus[]
  overridden_keys: string[]
}

// Partial update for PATCH /config/ai — only non-null fields are applied.
export interface AIModelConfigUpdate {
  agent_default_model?: string
  agent_fallback_model?: string
  agent_temperature?: number
  agent_max_tokens?: number
  agent_thinking_budget?: number | null
  rag_embedding_provider?: 'openai' | 'ollama'
  rag_embedding_model?: string
  rag_embedding_dimension?: number
  ollama_base_url?: string
  ollama_embedding_model?: string
  openai_api_key?: string
  anthropic_api_key?: string
  google_api_key?: string
  force?: boolean
}

// One model pulled on the Ollama host.
export interface OllamaModel {
  name: string
  size_bytes: number | null
  family: string | null
}

// Connectivity status for one AI provider — GET /config/providers/health.
export interface ProviderHealth {
  provider: string
  reachable: boolean
  detail: string
  models: string[]
}

// =============================================================================
// ForecastOps Control Center — GET /ops/summary, GET /ops/retraining-candidates
// =============================================================================

// Liveness snapshot for the Control Center header.
export interface SystemHealth {
  api_ok: boolean
  database_connected: boolean
  latest_successful_job_at: string | null
}

// One bucket of a status histogram.
export interface StatusCount {
  status: string
  count: number
}

// Aggregated job-execution health.
export interface JobHealth {
  counts: StatusCount[]
  completed_today: number
  failed_total: number
  active_total: number
}

// Aggregated model-run health.
export interface RunHealth {
  counts: StatusCount[]
  success_rate: number | null
  failed_total: number
}

// PRP-36 — enum literal values mirror app/features/ops/schemas.py:StaleReason.
// 'feature_frame_version_mismatch' is the new value PRP-36 adds; surfaces as a
// distinct chip on the Ops page so operators can see a V-drift apart from a
// generic newer-run finding.
export type StaleReason =
  | 'newer_success_run'
  | 'artifact_not_verified'
  | 'run_not_success'
  | 'feature_frame_version_mismatch'

// Deployment-alias health with a staleness verdict.
export interface AliasHealth {
  alias_name: string
  run_id: string
  run_status: string
  model_type: string
  store_id: number
  product_id: number
  is_stale: boolean
  stale_reason: StaleReason | string | null
  wape: number | null
  /** PRP-36 — version of the alias's current run. */
  alias_feature_frame_version?: FeatureFrameVersion | null
  /** PRP-36 — version of the newest comparable run, when one exists. */
  comparable_run_feature_frame_version?: FeatureFrameVersion | null
}

// How current the underlying data and model state are.
export interface DataFreshness {
  latest_sales_date: string | null
  latest_job_completed_at: string | null
  latest_run_completed_at: string | null
}

// One entry in the "needs attention" list.
export interface AttentionItem {
  item_type: 'failed_job' | 'failed_run' | 'stale_alias'
  entity_id: string
  label: string
  detail: string
  occurred_at: string | null
}

// Aggregated operational summary — GET /ops/summary.
export interface OpsSummaryResponse {
  system: SystemHealth
  jobs: JobHealth
  runs: RunHealth
  aliases: AliasHealth[]
  freshness: DataFreshness
  attention_items: AttentionItem[]
  generated_at: string
}

// One (store, product) pair ranked for retraining.
export interface RetrainingCandidate {
  store_id: number
  product_id: number
  priority_score: number
  staleness_days: number
  wape: number | null
  latest_run_id: string | null
  latest_run_status: string | null
  reason: string
}

// Ranked retraining-candidate queue — GET /ops/retraining-candidates.
export interface RetrainingCandidatesResponse {
  candidates: RetrainingCandidate[]
  total_evaluated: number
  generated_at: string
}

// Forecast-error trend verdict for a (store, product) grain.
export type DriftDirection = 'improving' | 'stable' | 'degrading' | 'unknown'

// One run's WAPE observation in a grain's chronological history.
export interface WapePoint {
  run_id: string
  created_at: string
  wape: number | null
}

// Forecast-error health and drift verdict for one (store, product) grain.
export interface ModelHealthEntry {
  store_id: number
  product_id: number
  run_count: number
  latest_run_id: string | null
  latest_run_status: string | null
  latest_wape: number | null
  previous_wape: number | null
  wape_delta: number | null
  drift_direction: DriftDirection
  last_trained_at: string | null
  staleness_days: number
  wape_history: WapePoint[]
  /** PRP-36 — version of the alias's current run. */
  alias_feature_frame_version?: FeatureFrameVersion | null
  /** PRP-36 — version of the newest comparable run. */
  comparable_run_feature_frame_version?: FeatureFrameVersion | null
}

// Per-grain forecast-error health — GET /ops/model-health.
export interface ModelHealthResponse {
  entries: ModelHealthEntry[]
  total_evaluated: number
  generated_at: string
}

// ── Scenario Simulation / What-If Planner ──

// A relative price change over a future date window.
export interface PriceAssumption {
  change_pct: number
  start_date: string
  end_date: string
}

// A promotion of a given kind running over a future date window.
export interface PromotionAssumption {
  kind: 'pct_off' | 'bogo' | 'bundle' | 'markdown'
  start_date: string
  end_date: string
}

// Explicit holiday / event days that lift demand.
export interface HolidayAssumption {
  dates: string[]
}

// On-hand stock used only to derive a coverage verdict.
export interface InventoryAssumption {
  on_hand_units: number
}

// A forced product lifecycle stage for the horizon.
export interface LifecycleAssumption {
  stage: 'launch' | 'growth' | 'maturity' | 'decline'
}

// The full set of optional what-if assumptions.
export interface ScenarioAssumptions {
  price?: PriceAssumption | null
  promotion?: PromotionAssumption | null
  holiday?: HolidayAssumption | null
  inventory?: InventoryAssumption | null
  lifecycle?: LifecycleAssumption | null
}

// Request body for POST /scenarios/simulate.
export interface SimulateScenarioRequest {
  run_id: string
  horizon: number
  assumptions: ScenarioAssumptions
  name?: string | null
}

// Request body for POST /scenarios.
export interface CreateScenarioRequest {
  name: string
  run_id: string
  horizon: number
  assumptions: ScenarioAssumptions
  tags?: string[]
  cloned_from?: string | null
}

// Whether projected demand is covered by on-hand stock.
export type CoverageVerdict = 'covered' | 'at_risk' | 'stockout' | 'unknown'

// One horizon day: baseline vs. scenario demand and the factor applied.
export interface ScenarioPoint {
  date: string
  baseline: number
  scenario: number
  delta: number
  applied_factor: number
}

// A full baseline-vs-scenario comparison — POST /scenarios/simulate.
export interface ScenarioComparison {
  store_id: number
  product_id: number
  model_type: string
  horizon: number
  points: ScenarioPoint[]
  baseline_total_units: number
  scenario_total_units: number
  units_delta: number
  units_delta_pct: number
  unit_price_used: number
  baseline_revenue: number
  scenario_revenue: number
  revenue_delta: number
  coverage_verdict: CoverageVerdict
  // 'heuristic' = a deterministic post-forecast multiplier; 'model_exogenous'
  // = a re-forecast through a feature-consuming regression model (PRP-27).
  method: 'heuristic' | 'model_exogenous'
  disclaimer: string
  generated_at: string
}

// A persisted scenario plan with its embedded comparison snapshot.
export interface ScenarioPlanResponse {
  scenario_id: string
  name: string
  store_id: number
  product_id: number
  run_id: string
  horizon: number
  method: string
  created_at: string
  assumptions: ScenarioAssumptions
  comparison: ScenarioComparison
  tags: string[]
  cloned_from: string | null
}

// A compact row in the saved-plans list.
export interface ScenarioListItem {
  scenario_id: string
  name: string
  store_id: number
  product_id: number
  horizon: number
  units_delta: number
  revenue_delta: number
  created_at: string
  tags: string[]
}

// A page of saved scenario plans — GET /scenarios.
export interface ScenarioListResponse {
  scenarios: ScenarioListItem[]
  total: number
}

// Metric a multi-scenario comparison ranks by.
export type RankBy = 'revenue_delta' | 'units_delta'

// Request body for POST /scenarios/compare.
export interface CompareScenariosRequest {
  scenario_ids: string[]
  rank_by?: RankBy
}

// One saved plan's headline numbers within a multi-scenario comparison.
export interface ScenarioComparisonRow {
  scenario_id: string
  name: string
  units_delta: number
  revenue_delta: number
  coverage_verdict: CoverageVerdict
  rank: number
}

// A baseline compared against 2-5 saved scenarios — POST /scenarios/compare.
export interface MultiScenarioComparison {
  baseline_total_units: number
  baseline_revenue: number
  rank_by: RankBy
  scenarios: ScenarioComparisonRow[]
  // Date-keyed merged rows: each carries 'date', 'baseline', and one numeric
  // entry per scenario name.
  chart_series: Record<string, number | string>[]
}

// =============================================================================
// Explainability — PRP-28 forecast explanation & driver attribution
// =============================================================================

// Qualitative confidence band for a forecast explanation.
export type ConfidenceLevel = 'high' | 'medium' | 'low'

// One named, interpretable demand driver behind a forecast. A driver with
// contribution === 0 is informational context the model does not consume.
export interface DriverContribution {
  name: string
  feature_value: number
  contribution: number
  direction: 'positive' | 'negative' | 'neutral'
  description: string
}

// An advisory retail signal correlated with the forecast — never a causal claim.
export interface ReasonCode {
  code: string
  severity: 'info' | 'warn'
  detail: string
}

// A structured, rule-based explanation of a baseline h=1 forecast —
// GET /explain/runs/{run_id}, GET /explain/jobs/{job_id}, POST /explain/forecast.
export interface ForecastExplanation {
  store_id: number
  product_id: number
  model_type: string
  method: 'rule_based'
  forecast_value: number
  drivers: DriverContribution[]
  reason_codes: ReasonCode[]
  confidence: ConfidenceLevel
  caveats: string[]
  agent_summary: string
  as_of_date: string // ISO date
  generated_at: string // ISO datetime
}

// =============================================================================
// Model Selection (Champion Selector) — backend slice app/features/model_selection
// =============================================================================
//
// The FULL workflow contract is declared here so Slices B/C add BEHAVIOR, not
// type definitions. Slice A CONSUMES only `ModelCatalogResponse`,
// `PairAvailability`, and `SplitConfig` (read-only). Everything tagged
// DECLARED-FOR-LATER is wired by Slice B (async run + results) and Slice C
// (train / predict / business summary / override / promotion).

export type ModelSelectionStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'partial'
  | 'failed'
  | 'cancelled' // Slice B — async cancel terminal state
export type CandidateStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'
export type RankingMetric = 'wape' | 'smape' | 'mae' | 'bias'
export type AvailabilityStatus = 'ready' | 'limited' | 'unusable'
// `ConfidenceLevel` ('high' | 'medium' | 'low') is reused from the
// Explainability section above — the backend uses the same enum.

// Backtest split config — mirrors `app/features/backtesting/schemas.py`
// `SplitConfig` EXACTLY (bounds enforced client-side so the assembled run
// request is always valid for Slice B).
export type SplitStrategy = 'expanding' | 'sliding'
export interface SplitConfig {
  strategy: SplitStrategy // def 'expanding'
  n_splits: number // 2..20, def 5
  min_train_size: number // >= 7, def 30
  gap: number // 0..30, def 0
  horizon: number // 1..90, def 14; must be > gap; kept === forecast_horizon
}

// --- CONSUMED in Slice A ---------------------------------------------------

export interface CandidateModelInfo {
  model_type: string
  label: string
  family: ModelFamily
  feature_aware: boolean
  /** lightgbm/xgboost — opt-in extra may be absent at runtime. */
  requires_extra: boolean
  default_params: Record<string, unknown>
  /** false for feature-aware models (the predict path rejects them). */
  supports_auto_predict: boolean
  description: string
}

export interface ModelCatalogResponse {
  models: CandidateModelInfo[]
  default_candidate_model_types: string[]
}

export interface PairAvailability {
  store_id: number
  product_id: number
  first_sales_date: string | null
  last_sales_date: string | null
  observed_days: number
  expected_calendar_days: number
  coverage_ratio: number
  missing_days: number
  zero_sale_days: number
  promotion_days: number | null
  average_daily_demand: number
  status: AvailabilityStatus
  recommended_split_config: SplitConfig
  warnings: string[]
}

// --- DECLARED-FOR-LATER (Slices B/C wire behavior on these) ----------------

export interface SelectionWindow {
  start_date: string // ISO date (inclusive)
  end_date: string // ISO date (inclusive)
}

export interface CandidateModelConfig {
  model_type: string
  params: Record<string, unknown>
}

export interface RankingPolicy {
  minimum_sample_size: number
  high_confidence_rel_improvement: number
  max_acceptable_abs_bias: number
}

export interface ModelSelectionRunRequest {
  store_id: number
  product_id: number
  selection_window: SelectionWindow
  forecast_horizon: number
  ranking_metric: RankingMetric
  split_config: SplitConfig
  candidate_models: CandidateModelConfig[]
  feature_frame_version: number // 1 | 2 (Slice A always 1)
  feature_groups: string[] | null // only valid when feature_frame_version === 2
  ranking_policy?: RankingPolicy
  // Slice A sets BOTH false. The async run path (Slice B `POST /runs`) treats
  // them as NO-OPS, and Slice C owns explicit train/predict — so these two
  // fields stay false throughout the UI flow and are never surfaced as toggles.
  auto_train_winner: boolean
  auto_predict: boolean
}

export interface ModelRankEntry {
  rank: number | null
  model_type: string
  params: Record<string, unknown>
  included: boolean
  exclusion_reason: string | null
  metrics: Record<string, number> | null
}

export interface WinnerSummary {
  model_type: string
  params: Record<string, unknown>
  metrics: Record<string, number>
  rank: number
}

export interface ModelSelectionChartData {
  wape_by_model: Record<string, number>
  bias_by_model: Record<string, number>
  fold_stability: Record<string, number[]>
  winner_actual_vs_predicted: unknown[]
}

export interface ModelSelectionForecastSummary {
  points: Record<string, unknown>[]
  total_demand: number
  average_demand: number
  horizon: number
  // Slice C — additive peak/low day (null on legacy snapshots).
  peak_date?: string | null
  peak_demand?: number | null
  low_date?: string | null
  low_demand?: number | null
}

// Slice B — live async progress on a selection run.
export interface CandidateProgress {
  candidate_id: string
  ordinal: number
  model_type: string
  status: CandidateStatus
  error: string | null
  started_at: string | null
  completed_at: string | null
  duration_ms: number | null
}

export interface SelectionProgress {
  total: number
  pending: number
  running: number
  completed: number
  failed: number
  cancelled: number
}

export interface ModelSelectionRunResponse {
  selection_id: string
  store_id: number
  product_id: number
  status: ModelSelectionStatus
  selection_window: SelectionWindow
  forecast_horizon: number
  ranking_metric: string
  availability: PairAvailability | null
  ranking: ModelRankEntry[]
  winner: WinnerSummary | null
  recommendation_confidence: ConfidenceLevel | null
  confidence_reasons: string[]
  chart_data: ModelSelectionChartData | null
  final_model: Record<string, unknown> | null
  forecast: ModelSelectionForecastSummary | null
  business_summary: Record<string, unknown> | null
  error_message: string | null
  created_at: string // ISO datetime
  // Slice B — additive async fields (null/empty on a legacy sync `/run` row).
  started_at?: string | null
  completed_at: string | null
  progress?: SelectionProgress | null
  candidate_progress?: CandidateProgress[]
}

// Slice B — 202 response from `POST /model-selection/runs` (additive superset).
export interface SubmitRunResponse extends ModelSelectionRunResponse {
  monitor_url: string
  cancel_url: string
}

// Slice C — forecast decision, override, and promotion contracts.

/** `POST /model-selection/{id}/train-selected` body (override). */
export interface TrainSelectedRequest {
  model_type: string
  override_reason?: string | null
}

/** Optional `POST /model-selection/{id}/predict` body. */
export interface ForecastDecisionParams {
  lead_time_days: number
  service_level: number
}

/** Deterministic, labeled inventory-decision heuristic (never feeds ranking). */
export interface ForecastDecision {
  method: 'heuristic'
  lead_time_days: number
  service_level: number
  z_value: number
  sigma_daily_demand: number
  expected_demand_over_lead_time: number
  safety_stock: number
  reorder_point: number
  bias_risk_text: string
  caveats: string[]
}

/** `POST /model-selection/{id}/train-winner` and `/train-selected` response. */
export interface TrainWinnerResponse {
  selection_id: string
  model_type: string
  model_path: string
  is_override: boolean
  override_warning: string | null
}

/** `POST /model-selection/{id}/predict` response (forecast + decision). */
export interface PredictWinnerResponse {
  selection_id: string
  forecast: ModelSelectionForecastSummary
  decision: ForecastDecision | null
}

/** `POST /model-selection/{id}/promote` body (approval-gated). */
export interface PromoteRequest {
  alias_name: string
  approved_by: string
  acknowledge_non_recommended?: boolean
  description?: string | null
}

/** `POST /model-selection/{id}/promote` response. */
export interface PromoteResponse {
  selection_id: string
  alias_name: string
  run_id: string
  run_status: string
  model_type: string
  is_override: boolean
  promoted_at: string // ISO datetime
}
