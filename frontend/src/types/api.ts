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
