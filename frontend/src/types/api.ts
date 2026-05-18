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

export interface ModelRun {
  run_id: string
  status: RunStatus
  model_type: string
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
}

// Start frame for WS /demo/stream and request body for POST /demo/run.
export interface DemoRunRequest {
  seed?: number
  reset?: boolean
  skip_seed?: boolean
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
