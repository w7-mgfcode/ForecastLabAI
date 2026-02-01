# PRP-11B: ForecastLab Dashboard — Architecture & Core Features

**Feature**: INITIAL-11B.md — Architecture & Features Implementation
**Status**: Ready for Implementation
**Confidence Score**: 8.5/10
**Prerequisites**: PRP-11A (Frontend Setup) COMPLETED

---

## Goal

Implement the core ForecastLab Dashboard architecture and features:

1. **App Shell** with top navigation + route-level tabs (not sidebar)
2. **React Router** with protected routes and lazy loading
3. **API Client** with typed fetch wrapper and error handling
4. **TanStack Query** hooks for all backend endpoints
5. **Data Explorer** with reusable DataTable (server-side pagination)
6. **Time Series Charts** using shadcn/ui chart component
7. **Agent Chat Interface** with WebSocket streaming
8. **Admin Panel** for RAG sources and deployment aliases
9. **Dark/Light Theme** toggle with persistence

This PRP builds on the scaffolded frontend from PRP-11A and implements the functional architecture.

---

## Why

- **User Experience**: Replace CLI with intuitive data exploration and visualization
- **Portfolio Demonstration**: Full-stack React 19 + FastAPI integration
- **Operational**: Admin panel for system management without raw API calls
- **Agent Interaction**: Chat interface for RAG queries and experiment orchestration

---

## What

### Route Structure

| Route | Component | API Endpoint(s) |
|-------|-----------|-----------------|
| `/` | DashboardPage | `GET /analytics/kpis` |
| `/explorer/sales` | SalesExplorerPage | `GET /analytics/drilldowns` |
| `/explorer/stores` | StoresExplorerPage | `GET /dimensions/stores` |
| `/explorer/products` | ProductsExplorerPage | `GET /dimensions/products` |
| `/explorer/runs` | RunsExplorerPage | `GET /registry/runs` |
| `/explorer/jobs` | JobsMonitorPage | `GET /jobs` |
| `/visualize/forecast` | ForecastPage | Job results |
| `/visualize/backtest` | BacktestPage | Job results |
| `/chat` | ChatPage | `WS /agents/stream` |
| `/admin` | AdminPage | `GET /rag/sources`, `GET /registry/aliases` |

### Success Criteria

- [ ] App shell with NavigationMenu component and mobile Sheet drawer
- [ ] React Router configured with lazy-loaded routes
- [ ] API client with typed responses and RFC 7807 error handling
- [ ] TanStack Query hooks for all 10+ API endpoints
- [ ] DataTable component with server-side pagination (1-indexed)
- [ ] TimeSeriesChart component with actual/predicted lines
- [ ] WebSocket hook with reconnection and streaming support
- [ ] ChatMessage component with citations and tool call display
- [ ] Theme toggle with next-themes and localStorage persistence
- [ ] All TypeScript strict checks pass
- [ ] `pnpm build` succeeds without errors
- [ ] Responsive design (mobile-first)

---

## All Needed Context

### Documentation & References

```yaml
# MUST READ - Critical Documentation
- url: https://ui.shadcn.com/docs/components/data-table
  why: "Server-side DataTable pattern with TanStack Table"
  critical: "Use manualPagination=true, pass pageCount, onPaginationChange"

- url: https://tanstack.com/query/latest/docs/framework/react/guides/paginated-queries
  why: "TanStack Query v5 pagination with placeholderData"
  critical: "Use keepPreviousData function or placeholderData: (prev) => prev"

- url: https://tanstack.com/query/latest/docs/framework/react/guides/migrating-to-v5
  why: "v5 migration - keepPreviousData → placeholderData"
  critical: "Import keepPreviousData from @tanstack/react-query"

- url: https://tanstack.com/table/latest/docs/guide/pagination
  why: "Server-side pagination with manualPagination=true"
  critical: "pageCount must be passed, use onPaginationChange callback"

- url: https://ui.shadcn.com/docs/components/chart
  why: "shadcn/ui chart wrapper for Recharts"
  critical: "Uses ChartContainer, ChartTooltip, ChartConfig pattern"

- url: https://tailwindcss.com/blog/tailwindcss-v4
  why: "Tailwind CSS 4 CSS-first configuration"
  critical: "Use @import 'tailwindcss' NOT @tailwind directives"

# Existing Codebase Patterns
- file: frontend/src/components/ui/table.tsx
  why: "Existing table primitives - TableHead, TableRow, TableCell"

- file: frontend/src/components/ui/chart.tsx
  why: "Existing chart component with ChartContainer, ChartTooltip"

- file: frontend/src/components/ui/button.tsx
  why: "Button variants pattern with CVA"

- file: frontend/vite.config.ts
  why: "API proxy configured - /api/* → localhost:8123"
```

### Current Frontend Structure (After PRP-11A)

```
frontend/
├── src/
│   ├── components/
│   │   └── ui/                     # 26 shadcn/ui components installed
│   │       ├── button.tsx          # CVA variants pattern
│   │       ├── card.tsx            # Card, CardHeader, CardContent
│   │       ├── chart.tsx           # ChartContainer, ChartTooltip
│   │       ├── navigation-menu.tsx # Top nav component
│   │       ├── sheet.tsx           # Mobile drawer
│   │       ├── table.tsx           # Table primitives
│   │       ├── tabs.tsx            # Route-level tabs
│   │       └── ... (20+ more)
│   ├── lib/
│   │   └── utils.ts                # cn() utility
│   ├── App.tsx                     # Demo - needs replacement
│   ├── main.tsx                    # Entry point
│   └── index.css                   # Tailwind + theme vars
├── .env.example                    # VITE_API_BASE_URL, VITE_WS_URL
├── components.json                 # shadcn/ui config (New York style)
├── vite.config.ts                  # Tailwind plugin + /api proxy
└── package.json                    # All deps installed
```

### Desired Codebase Tree (Files to Create)

```
frontend/src/
├── components/
│   ├── ui/                         # EXISTING - Don't modify
│   ├── layout/                     # NEW: App shell
│   │   ├── app-shell.tsx           # Main layout with nav
│   │   ├── top-nav.tsx             # NavigationMenu + mobile Sheet
│   │   └── theme-toggle.tsx        # Dark/light toggle button
│   ├── data-table/                 # NEW: Reusable DataTable
│   │   ├── data-table.tsx          # Main component
│   │   ├── data-table-pagination.tsx
│   │   └── data-table-toolbar.tsx  # Filters row
│   ├── charts/                     # NEW: Chart wrappers
│   │   ├── time-series-chart.tsx   # Actual vs Predicted
│   │   ├── kpi-card.tsx            # Dashboard KPI display
│   │   └── backtest-folds-chart.tsx
│   ├── chat/                       # NEW: Agent chat
│   │   ├── chat-message.tsx        # Message bubble with citations
│   │   ├── chat-input.tsx          # Text input with send
│   │   └── tool-call-display.tsx   # Collapsible tool calls
│   └── common/                     # NEW: Shared components
│       ├── status-badge.tsx        # SUCCESS/FAILED/PENDING badges
│       ├── date-range-picker.tsx   # Calendar popover
│       └── error-display.tsx       # Error state component
├── hooks/                          # NEW: TanStack Query hooks
│   ├── use-stores.ts
│   ├── use-products.ts
│   ├── use-kpis.ts
│   ├── use-drilldowns.ts
│   ├── use-runs.ts
│   ├── use-aliases.ts
│   ├── use-jobs.ts
│   ├── use-rag-sources.ts
│   └── use-websocket.ts            # WebSocket with reconnect
├── lib/                            # EXTEND existing
│   ├── utils.ts                    # EXISTING - Keep as is
│   ├── api.ts                      # NEW: Typed fetch client
│   ├── query-client.ts             # NEW: TanStack Query config
│   └── constants.ts                # NEW: Route paths, etc.
├── pages/                          # NEW: Route pages
│   ├── dashboard.tsx
│   ├── explorer/
│   │   ├── sales.tsx
│   │   ├── stores.tsx
│   │   ├── products.tsx
│   │   ├── runs.tsx
│   │   └── jobs.tsx
│   ├── visualize/
│   │   ├── forecast.tsx
│   │   └── backtest.tsx
│   ├── chat.tsx
│   └── admin.tsx
├── types/                          # NEW: TypeScript types
│   ├── api.ts                      # Backend response types
│   └── index.ts                    # Re-exports
├── providers/                      # NEW: Context providers
│   └── theme-provider.tsx          # next-themes wrapper
├── App.tsx                         # REPLACE: Router + providers
└── main.tsx                        # KEEP: Entry point
```

### Backend API Summary (From Agent Exploration)

```typescript
// ALL LIST ENDPOINTS: 1-indexed pagination
// Query: ?page=1&page_size=20 (max 100)
// Response: { items[], total, page, page_size }

// Dimensions
GET /dimensions/stores   → { stores[], total, page, page_size }
GET /dimensions/products → { products[], total, page, page_size }

// Analytics
GET /analytics/kpis?start_date=&end_date= → { metrics: KPIMetrics, ... }
GET /analytics/drilldowns?dimension=store&start_date=&end_date= → { items[], ... }

// Registry
GET /registry/runs      → { runs[], total, page, page_size }
PATCH /registry/runs/{run_id} → RunResponse
GET /registry/compare/{a}/{b} → { run_a, run_b, config_diff, metrics_diff }
GET /registry/aliases   → AliasResponse[]
POST /registry/aliases  → AliasResponse
DELETE /registry/aliases/{name} → 204

// Jobs
GET /jobs               → { jobs[], total, page, page_size }
POST /jobs              → JobResponse (202 Accepted)
DELETE /jobs/{id}       → 204 (cancel pending only)

// RAG
GET /rag/sources        → { sources[], total_sources, total_chunks }
POST /rag/index         → IndexResponse (201)
DELETE /rag/sources/{id} → DeleteResponse

// Agents
POST /agents/sessions   → SessionResponse (201)
POST /agents/sessions/{id}/chat → ChatResponse
WebSocket /agents/stream → Streaming events
```

### Known Gotchas & Library Quirks

```typescript
// CRITICAL: TanStack Query v5 - keepPreviousData migration
// OLD (v4): useQuery({ queryKey, queryFn, keepPreviousData: true })
// NEW (v5): useQuery({ queryKey, queryFn, placeholderData: keepPreviousData })
// Import: import { keepPreviousData } from '@tanstack/react-query'

// CRITICAL: TanStack Table v8 - API changes
// Use: useReactTable() NOT useTable()
// Require: getCoreRowModel() import and usage
// Server-side: manualPagination: true, manualSorting: true

// CRITICAL: Pagination is 1-indexed from backend
// Backend: page=1 is first page
// TanStack Table: pageIndex=0 is first page
// Convert: page = pageIndex + 1

// CRITICAL: Vite environment variables
// Access: import.meta.env.VITE_API_BASE_URL
// NOT: process.env.VITE_API_BASE_URL (Node.js only)
// Prefix: Must start with VITE_ to be exposed

// CRITICAL: WebSocket reconnection
// Browser WebSocket has NO auto-reconnect
// Implement exponential backoff manually
// Use AbortController for cleanup

// CRITICAL: next-themes with Vite
// Requires ThemeProvider with attribute="class"
// Add storageKey for localStorage persistence
// Wrap at App root level

// CRITICAL: Decimal handling from backend
// Backend sends Decimal as string: "1234.56"
// Parse: parseFloat(value)
// Format: new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

// CRITICAL: shadcn/ui chart colors
// Use CSS variables: var(--chart-1) through var(--chart-5)
// Already defined in index.css from PRP-11A
// ChartConfig maps dataKey to label and color
```

---

## Implementation Blueprint

### Task Overview

| # | Task | Description | Files Created |
|---|------|-------------|---------------|
| 1 | Create TypeScript types | Match backend schemas | `types/api.ts`, `types/index.ts` |
| 2 | Create API client | Typed fetch with error handling | `lib/api.ts` |
| 3 | Setup TanStack Query | QueryClient config | `lib/query-client.ts` |
| 4 | Create query hooks | All API endpoint hooks | `hooks/*.ts` |
| 5 | Create theme provider | next-themes wrapper | `providers/theme-provider.tsx` |
| 6 | Create app shell | Nav + layout | `components/layout/*.tsx` |
| 7 | Create DataTable | Reusable server-side table | `components/data-table/*.tsx` |
| 8 | Create common components | Badge, DatePicker, Error | `components/common/*.tsx` |
| 9 | Create chart components | TimeSeriesChart, KPICard | `components/charts/*.tsx` |
| 10 | Create chat components | Message, Input, ToolCall | `components/chat/*.tsx` |
| 11 | Create pages | All route pages | `pages/*.tsx` |
| 12 | Setup router | React Router + lazy load | `App.tsx` |
| 13 | Integration test | Verify with backend | Manual verification |

---

### Task 1: Create TypeScript Types

**File**: `frontend/src/types/api.ts`

```typescript
// === Pagination ===
export interface PaginatedResponse<T> {
  total: number
  page: number
  page_size: number
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
```

**File**: `frontend/src/types/index.ts`

```typescript
export * from './api'
```

---

### Task 2: Create API Client

**File**: `frontend/src/lib/api.ts`

```typescript
import type { ProblemDetail } from '@/types/api'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8123'

interface RequestConfig {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
  params?: Record<string, string | number | boolean | undefined | null>
  signal?: AbortSignal
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public detail?: ProblemDetail
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function api<T>(endpoint: string, config: RequestConfig = {}): Promise<T> {
  const { method = 'GET', body, params, signal } = config

  const url = new URL(`${API_BASE_URL}${endpoint}`)
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        url.searchParams.set(key, String(value))
      }
    })
  }

  const response = await fetch(url.toString(), {
    method,
    headers: {
      'Content-Type': 'application/json',
    },
    body: body ? JSON.stringify(body) : undefined,
    signal,
  })

  // Handle 204 No Content
  if (response.status === 204) {
    return undefined as T
  }

  const data = await response.json()

  if (!response.ok) {
    const detail = data as ProblemDetail
    throw new ApiError(
      detail.detail || response.statusText,
      response.status,
      detail
    )
  }

  return data as T
}

// Helper for consistent error messages
export function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.detail?.detail || error.message
  }
  if (error instanceof Error) {
    return error.message
  }
  return 'An unexpected error occurred'
}
```

---

### Task 3: Setup TanStack Query

**File**: `frontend/src/lib/query-client.ts`

```typescript
import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      gcTime: 10 * 60 * 1000,   // 10 minutes (formerly cacheTime)
      retry: 1,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 0,
    },
  },
})
```

---

### Task 4: Create Query Hooks

**File**: `frontend/src/hooks/use-stores.ts`

```typescript
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { StoreListResponse } from '@/types/api'

interface UseStoresParams {
  page: number
  pageSize: number
  region?: string
  storeType?: string
  search?: string
  enabled?: boolean
}

export function useStores({
  page,
  pageSize,
  region,
  storeType,
  search,
  enabled = true,
}: UseStoresParams) {
  return useQuery({
    queryKey: ['stores', { page, pageSize, region, storeType, search }],
    queryFn: () =>
      api<StoreListResponse>('/dimensions/stores', {
        params: {
          page,
          page_size: pageSize,
          region,
          store_type: storeType,
          search: search && search.length >= 2 ? search : undefined,
        },
      }),
    placeholderData: keepPreviousData,
    enabled,
  })
}

export function useStore(storeId: number, enabled = true) {
  return useQuery({
    queryKey: ['stores', storeId],
    queryFn: () => api<StoreListResponse['stores'][0]>(`/dimensions/stores/${storeId}`),
    enabled,
  })
}
```

**File**: `frontend/src/hooks/use-products.ts`

```typescript
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { ProductListResponse } from '@/types/api'

interface UseProductsParams {
  page: number
  pageSize: number
  category?: string
  brand?: string
  search?: string
  enabled?: boolean
}

export function useProducts({
  page,
  pageSize,
  category,
  brand,
  search,
  enabled = true,
}: UseProductsParams) {
  return useQuery({
    queryKey: ['products', { page, pageSize, category, brand, search }],
    queryFn: () =>
      api<ProductListResponse>('/dimensions/products', {
        params: {
          page,
          page_size: pageSize,
          category,
          brand,
          search: search && search.length >= 2 ? search : undefined,
        },
      }),
    placeholderData: keepPreviousData,
    enabled,
  })
}
```

**File**: `frontend/src/hooks/use-kpis.ts`

```typescript
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { KPIResponse } from '@/types/api'

interface UseKPIsParams {
  startDate: string
  endDate: string
  storeId?: number
  productId?: number
  category?: string
  enabled?: boolean
}

export function useKPIs({
  startDate,
  endDate,
  storeId,
  productId,
  category,
  enabled = true,
}: UseKPIsParams) {
  return useQuery({
    queryKey: ['kpis', { startDate, endDate, storeId, productId, category }],
    queryFn: () =>
      api<KPIResponse>('/analytics/kpis', {
        params: {
          start_date: startDate,
          end_date: endDate,
          store_id: storeId,
          product_id: productId,
          category,
        },
      }),
    enabled: enabled && !!startDate && !!endDate,
  })
}
```

**File**: `frontend/src/hooks/use-runs.ts`

```typescript
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { RunListResponse, ModelRun, Alias, RunCompareResponse } from '@/types/api'

interface UseRunsParams {
  page: number
  pageSize: number
  modelType?: string
  status?: string
  storeId?: number
  productId?: number
  enabled?: boolean
}

export function useRuns({
  page,
  pageSize,
  modelType,
  status,
  storeId,
  productId,
  enabled = true,
}: UseRunsParams) {
  return useQuery({
    queryKey: ['runs', { page, pageSize, modelType, status, storeId, productId }],
    queryFn: () =>
      api<RunListResponse>('/registry/runs', {
        params: {
          page,
          page_size: pageSize,
          model_type: modelType,
          status,
          store_id: storeId,
          product_id: productId,
        },
      }),
    placeholderData: keepPreviousData,
    enabled,
  })
}

export function useRun(runId: string, enabled = true) {
  return useQuery({
    queryKey: ['runs', runId],
    queryFn: () => api<ModelRun>(`/registry/runs/${runId}`),
    enabled: enabled && !!runId,
  })
}

export function useCompareRuns(runIdA: string, runIdB: string, enabled = false) {
  return useQuery({
    queryKey: ['runs', 'compare', runIdA, runIdB],
    queryFn: () => api<RunCompareResponse>(`/registry/compare/${runIdA}/${runIdB}`),
    enabled: enabled && !!runIdA && !!runIdB,
  })
}

export function useAliases() {
  return useQuery({
    queryKey: ['aliases'],
    queryFn: () => api<Alias[]>('/registry/aliases'),
  })
}

export function useCreateAlias() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: { alias_name: string; run_id: string; description?: string }) =>
      api<Alias>('/registry/aliases', { method: 'POST', body: data }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['aliases'] })
    },
  })
}

export function useDeleteAlias() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (aliasName: string) =>
      api<void>(`/registry/aliases/${aliasName}`, { method: 'DELETE' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['aliases'] })
    },
  })
}
```

**File**: `frontend/src/hooks/use-jobs.ts`

```typescript
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { JobListResponse, Job, JobCreate } from '@/types/api'

interface UseJobsParams {
  page: number
  pageSize: number
  jobType?: string
  status?: string
  enabled?: boolean
}

export function useJobs({
  page,
  pageSize,
  jobType,
  status,
  enabled = true,
}: UseJobsParams) {
  return useQuery({
    queryKey: ['jobs', { page, pageSize, jobType, status }],
    queryFn: () =>
      api<JobListResponse>('/jobs', {
        params: {
          page,
          page_size: pageSize,
          job_type: jobType,
          status,
        },
      }),
    placeholderData: keepPreviousData,
    refetchInterval: 5000, // Poll every 5 seconds
    enabled,
  })
}

export function useJob(jobId: string, enabled = true) {
  return useQuery({
    queryKey: ['jobs', jobId],
    queryFn: () => api<Job>(`/jobs/${jobId}`),
    enabled: enabled && !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'pending' || status === 'running' ? 2000 : false
    },
  })
}

export function useCreateJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: JobCreate) =>
      api<Job>('/jobs', { method: 'POST', body: data }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })
}

export function useCancelJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (jobId: string) =>
      api<void>(`/jobs/${jobId}`, { method: 'DELETE' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })
}
```

**File**: `frontend/src/hooks/use-rag-sources.ts`

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { SourceListResponse } from '@/types/api'

export function useRagSources() {
  return useQuery({
    queryKey: ['rag-sources'],
    queryFn: () => api<SourceListResponse>('/rag/sources'),
  })
}

export function useDeleteRagSource() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (sourceId: string) =>
      api<void>(`/rag/sources/${sourceId}`, { method: 'DELETE' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['rag-sources'] })
    },
  })
}

export function useIndexDocument() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: { source_type: string; source_path: string; content?: string }) =>
      api<{ source_id: string; chunks_created: number }>('/rag/index', {
        method: 'POST',
        body: data,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['rag-sources'] })
    },
  })
}
```

**File**: `frontend/src/hooks/use-websocket.ts`

```typescript
import { useEffect, useRef, useState, useCallback } from 'react'

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

interface UseWebSocketOptions {
  onMessage?: (data: unknown) => void
  onError?: (error: Event) => void
  reconnectAttempts?: number
  reconnectInterval?: number
}

export function useWebSocket(url: string | null, options: UseWebSocketOptions = {}) {
  const {
    onMessage,
    onError,
    reconnectAttempts = 5,
    reconnectInterval = 3000,
  } = options

  const [status, setStatus] = useState<ConnectionStatus>('disconnected')
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectCountRef = useRef(0)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout>>()

  const connect = useCallback(() => {
    if (!url) return

    // Clear any pending reconnect
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
    }

    setStatus('connecting')
    const ws = new WebSocket(url)

    ws.onopen = () => {
      setStatus('connected')
      reconnectCountRef.current = 0
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data as string) as unknown
        onMessage?.(data)
      } catch {
        onMessage?.(event.data)
      }
    }

    ws.onerror = (error) => {
      setStatus('error')
      onError?.(error)
    }

    ws.onclose = () => {
      setStatus('disconnected')
      wsRef.current = null

      // Attempt reconnection with exponential backoff
      if (reconnectCountRef.current < reconnectAttempts) {
        const delay = reconnectInterval * Math.pow(2, reconnectCountRef.current)
        reconnectCountRef.current++
        reconnectTimeoutRef.current = setTimeout(connect, delay)
      }
    }

    wsRef.current = ws
  }, [url, onMessage, onError, reconnectAttempts, reconnectInterval])

  const disconnect = useCallback(() => {
    reconnectCountRef.current = reconnectAttempts // Prevent auto-reconnect
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
    }
    wsRef.current?.close()
    wsRef.current = null
    setStatus('disconnected')
  }, [reconnectAttempts])

  const send = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof data === 'string' ? data : JSON.stringify(data))
      return true
    }
    return false
  }, [])

  useEffect(() => {
    if (url) {
      connect()
    }
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      wsRef.current?.close()
    }
  }, [url, connect])

  return { status, send, disconnect, reconnect: connect }
}
```

---

### Task 5-12: Remaining Implementation

Due to length constraints, the remaining tasks (5-12) follow the same patterns as above. The key components are:

**Task 5: Theme Provider** - Use `next-themes` with `attribute="class"` and `storageKey="forecastlab-theme"`

**Task 6: App Shell** - Use `NavigationMenu` for desktop, `Sheet` for mobile drawer

**Task 7: DataTable** - Wrap TanStack Table with server-side pagination, use `manualPagination: true`

**Task 8: Common Components** - StatusBadge (CVA variants), DateRangePicker (Calendar + Popover)

**Task 9: Charts** - Use shadcn/ui `ChartContainer` with Recharts `LineChart`

**Task 10: Chat Components** - ChatMessage with Collapsible tool calls, scroll-area for history

**Task 11: Pages** - Implement each page following patterns from INITIAL-11C

**Task 12: Router** - React Router v7 with lazy loading via `React.lazy()`

---

## Validation Loop

### Level 1: TypeScript Compilation

```bash
cd frontend

# TypeScript strict check
pnpm tsc --noEmit

# Expected: No errors
```

### Level 2: Linting

```bash
cd frontend

# ESLint
pnpm lint

# Expected: No errors (or only shadcn component warnings)
```

### Level 3: Build Validation

```bash
cd frontend

# Production build
pnpm build

# Expected:
# ✓ dist/index.html created
# ✓ dist/assets/*.js created
# ✓ No TypeScript errors
```

### Level 4: Integration Test

```bash
# Terminal 1: Start backend
docker-compose up -d
uv run uvicorn app.main:app --port 8123

# Terminal 2: Start frontend
cd frontend
pnpm dev

# Manual verification:
# 1. Open http://localhost:5173
# 2. Navigate to /explorer/stores
# 3. Verify data loads (may need seeded data)
# 4. Test pagination (next/prev buttons)
# 5. Toggle dark mode
# 6. Test mobile view (resize browser)
# 7. Open browser DevTools - no console errors
```

---

## Final Validation Checklist

- [ ] All TypeScript types match backend schemas
- [ ] API client handles errors with RFC 7807 format
- [ ] TanStack Query hooks use `keepPreviousData` for pagination
- [ ] DataTable converts 0-indexed pageIndex to 1-indexed page
- [ ] WebSocket hook implements exponential backoff reconnection
- [ ] Theme toggle persists to localStorage
- [ ] NavigationMenu renders on desktop
- [ ] Sheet drawer works on mobile
- [ ] Charts use ChartContainer with CSS variable colors
- [ ] All pages render without errors
- [ ] `pnpm build` succeeds
- [ ] `pnpm tsc --noEmit` passes

---

## Integration Points

```yaml
BACKEND_DEPENDENCY:
  - Backend must be running on http://localhost:8123
  - Vite proxy configured: /api/* → localhost:8123
  - WebSocket: ws://localhost:8123/agents/stream

ENVIRONMENT_VARIABLES:
  - VITE_API_BASE_URL: Backend URL (default: http://localhost:8123)
  - VITE_WS_URL: WebSocket URL (default: ws://localhost:8123/agents/stream)
  - VITE_ENABLE_AGENT_CHAT: Feature flag for chat (default: true)
  - VITE_ENABLE_ADMIN_PANEL: Feature flag for admin (default: true)

SEEDED_DATA:
  - Stores: GET /dimensions/stores should return data
  - Products: GET /dimensions/products should return data
  - Sales: GET /analytics/drilldowns should return data (if seeded)
```

---

## Anti-Patterns to Avoid

- ❌ Don't use `keepPreviousData: true` — use `placeholderData: keepPreviousData`
- ❌ Don't use `useTable()` — use `useReactTable()` (TanStack Table v8)
- ❌ Don't forget `manualPagination: true` for server-side tables
- ❌ Don't use `process.env` — use `import.meta.env` for Vite
- ❌ Don't hardcode API URLs — always use environment variables
- ❌ Don't create WebSocket without cleanup — use useEffect return function
- ❌ Don't forget page conversion — backend is 1-indexed, TanStack is 0-indexed
- ❌ Don't use `@tailwind` directives — use `@import "tailwindcss"` (v4)

---

## Confidence Score Breakdown

| Area | Score | Rationale |
|------|-------|-----------|
| TypeScript Types | 9/10 | Backend schemas well-documented in routes.py |
| API Client | 9/10 | Simple fetch wrapper, error handling documented |
| TanStack Query | 9/10 | v5 migration well-documented, hooks straightforward |
| TanStack Table | 8/10 | Server-side pattern documented, 1-index conversion needed |
| shadcn/ui Components | 9/10 | Already installed, patterns in existing code |
| Charts | 8/10 | ChartContainer pattern exists in chart.tsx |
| WebSocket | 7/10 | Custom implementation, reconnection logic needed |
| Theme Toggle | 9/10 | next-themes well-documented for Vite |
| **Overall** | **8.5/10** | All foundational pieces in place |

---

## Notes for Implementing Agent

1. **Execute tasks in order** — types and API client must come first
2. **Don't modify existing ui/ components** — only create new files
3. **Test incrementally** — run `pnpm tsc --noEmit` after each task
4. **Use existing patterns** — button.tsx shows CVA variant pattern
5. **Convert pagination** — page = pageIndex + 1 for all API calls
6. **Import from @/** — use configured path aliases
7. **Check console for errors** — API errors should show ApiError details

---

## Documentation Sources

- [shadcn/ui Data Table](https://ui.shadcn.com/docs/components/data-table)
- [TanStack Query v5 Pagination](https://tanstack.com/query/latest/docs/framework/react/guides/paginated-queries)
- [TanStack Query v5 Migration](https://tanstack.com/query/latest/docs/framework/react/guides/migrating-to-v5)
- [TanStack Table Server-Side Pagination](https://tanstack.com/table/latest/docs/guide/pagination)
- [shadcn/ui Charts](https://ui.shadcn.com/docs/components/chart)
- [Tailwind CSS v4](https://tailwindcss.com/blog/tailwindcss-v4)
- [tablecn - Server-side shadcn table](https://github.com/sadmann7/tablecn)
