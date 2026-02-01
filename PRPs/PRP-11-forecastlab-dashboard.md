# PRP-11: ForecastLab Dashboard ("The Face")

**Feature**: INITIAL-11.md — ForecastLab Dashboard
**Status**: Ready for Implementation
**Confidence Score**: 7.5/10

---

## Goal

Build the ForecastLab Dashboard providing:
1. **Data Explorer** with server-side pagination, sorting, and filtering using TanStack Table
2. **Time Series Visualization** for forecasts and backtest results using Recharts
3. **Agent Chat Interface** with WebSocket streaming (depends on INITIAL-10 completion)
4. **Admin Panel** for RAG sources and deployment alias management

This is the "Face" layer that consumes the backend API (Phases 1-10) and provides a user-friendly interface.

---

## Why

- **User Experience**: No CLI required for data exploration and visualization
- **Agent Interaction**: Chat interface for RAG queries and experiment orchestration
- **Portfolio Value**: Demonstrates full-stack React 19 + FastAPI integration
- **Operational**: Admin panel for system management without API calls

---

## What

### Page Structure

| Route | Purpose | Backend Endpoints |
|-------|---------|-------------------|
| `/dashboard` | KPI summary cards | `GET /analytics/kpis` |
| `/explorer/sales` | Sales data table | `GET /analytics/drilldowns` |
| `/explorer/stores` | Store dimension table | `GET /dimensions/stores` |
| `/explorer/products` | Product dimension table | `GET /dimensions/products` |
| `/explorer/runs` | Model run leaderboard | `GET /registry/runs` |
| `/explorer/jobs` | Job monitor | `GET /jobs` |
| `/visualize/forecast` | Forecast chart | (via job results) |
| `/visualize/backtest` | Backtest fold visualization | (via job results) |
| `/chat` | Agent chat interface | `WS /agents/stream` |
| `/admin` | RAG sources + aliases | `GET /rag/sources`, `GET /registry/aliases` |

### Success Criteria

- [ ] Vite + React 19 project scaffolded with TypeScript strict mode
- [ ] shadcn/ui components installed and configured (Table, Card, Button, Dialog, etc.)
- [ ] TanStack Table with server-side pagination/sorting/filtering
- [ ] TanStack Query for all API calls with proper caching
- [ ] Recharts time series chart with actual/predicted lines
- [ ] WebSocket hook for agent chat streaming
- [ ] Dark/light theme toggle via shadcn/ui
- [ ] Responsive design (mobile-friendly)
- [ ] Error boundaries with retry functionality
- [ ] Lighthouse performance score > 90
- [ ] All TypeScript strict checks pass

---

## All Needed Context

### Documentation & References

```yaml
# React 19 + Vite Setup
- url: https://vite.dev/guide/
  why: "Vite project scaffolding, environment variables (import.meta.env)"
  section: "Getting Started, Env Variables"

- url: https://react.dev/
  why: "React 19 hooks (use(), useState, useEffect), Suspense, ErrorBoundary"

# shadcn/ui (CRITICAL - Primary Component Library)
- url: https://ui.shadcn.com/docs/installation/vite
  why: "Vite + React installation steps, tailwind.config.js setup"
  critical: "Must use 'npx shadcn@latest init' NOT 'shadcn-ui'"

- url: https://ui.shadcn.com/docs/components/data-table
  why: "TanStack Table integration pattern - the core pattern for all data tables"
  critical: "Uses @tanstack/react-table, manualPagination=true for server-side"

- url: https://ui.shadcn.com/docs/components/table
  why: "Base Table component used by Data Table"

- url: https://ui.shadcn.com/docs/dark-mode/vite
  why: "Dark mode setup with ThemeProvider"

# TanStack Table (Server-Side Pattern)
- url: https://tanstack.com/table/latest/docs/guide/pagination
  why: "Server-side pagination with manualPagination=true"
  critical: "pageCount must be passed, onPaginationChange callback"

- url: https://tanstack.com/table/latest/docs/guide/sorting
  why: "Server-side sorting with manualSorting=true"

- url: https://tanstack.com/table/latest/docs/guide/column-filtering
  why: "Server-side filtering with manualFiltering=true"

# TanStack Query (Data Fetching)
- url: https://tanstack.com/query/latest/docs/framework/react/guides/queries
  why: "useQuery pattern with queryKey and queryFn"

- url: https://tanstack.com/query/latest/docs/framework/react/guides/paginated-queries
  why: "keepPreviousData for smooth pagination transitions"

- url: https://tanstack.com/query/latest/docs/framework/react/guides/mutations
  why: "useMutation for POST/DELETE/PATCH operations"

# Recharts
- url: https://recharts.org/en-US/api/LineChart
  why: "Time series visualization with LineChart, XAxis, YAxis"

- url: https://recharts.org/en-US/api/Tooltip
  why: "Interactive tooltips"

- url: https://recharts.org/en-US/examples/SimpleLineChart
  why: "Basic example to follow"

# Tailwind CSS 4
- url: https://tailwindcss.com/docs/installation/using-vite
  why: "Tailwind 4 setup with Vite"

# WebSocket (for Agent Chat)
- url: https://developer.mozilla.org/en-US/docs/Web/API/WebSocket
  why: "Native WebSocket API - useWebSocket custom hook pattern"
```

### Backend API Contract Summary

```typescript
// ALL LIST ENDPOINTS USE THIS PAGINATION PATTERN:
// Query params: page (1-indexed), page_size (max 100)
// Response: { items[], total, page, page_size }

// Dimensions
GET /dimensions/stores?page=1&page_size=20&region=&store_type=&search=
// Response: StoreListResponse { stores[], total, page, page_size }

GET /dimensions/products?page=1&page_size=20&category=&brand=&search=
// Response: ProductListResponse { products[], total, page, page_size }

// Analytics
GET /analytics/kpis?start_date=&end_date=&store_id=&product_id=&category=
// Response: KPIResponse { metrics: KPIMetrics, start_date, end_date, ... }

GET /analytics/drilldowns?dimension=store&start_date=&end_date=&max_items=20
// Response: DrilldownResponse { dimension, items[], total_items, ... }

// Registry
GET /registry/runs?page=1&page_size=20&model_type=&status=&store_id=&product_id=
// Response: RunListResponse { runs[], total, page, page_size }

GET /registry/compare/{run_id_a}/{run_id_b}
// Response: RunCompareResponse { run_a, run_b, config_diff, metrics_diff }

POST /registry/aliases
// Body: { alias_name, run_id, description }
// Response: AliasResponse

GET /registry/aliases
// Response: AliasResponse[]

// Jobs
GET /jobs?page=1&page_size=20&job_type=&status=
// Response: JobListResponse { jobs[], total, page, page_size }

POST /jobs
// Body: { job_type: 'train'|'predict'|'backtest', params: {...} }
// Response: JobResponse (202 ACCEPTED)

DELETE /jobs/{job_id}
// Response: 204 NO CONTENT (only for pending jobs)

// Error Responses (RFC 7807)
// All errors return: { type, title, status, detail, instance, errors?, code, request_id }
```

### Current Codebase Tree

```
.
├── alembic/
├── app/
│   ├── core/
│   ├── features/
│   │   ├── analytics/     # GET /analytics/kpis, /drilldowns
│   │   ├── backtesting/   # POST /backtesting/run
│   │   ├── dimensions/    # GET /dimensions/stores, /products
│   │   ├── forecasting/   # POST /forecasting/train, /predict
│   │   ├── jobs/          # POST/GET/DELETE /jobs
│   │   └── registry/      # CRUD /registry/runs, /aliases
│   └── main.py
├── docs/
├── examples/
├── PRPs/
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

### Desired Codebase Tree (Files to Create)

```
frontend/                        # NEW: React 19 + Vite project
├── public/
│   └── favicon.ico
├── src/
│   ├── components/
│   │   ├── ui/                  # shadcn/ui components (auto-generated)
│   │   │   ├── button.tsx
│   │   │   ├── card.tsx
│   │   │   ├── dialog.tsx
│   │   │   ├── dropdown-menu.tsx
│   │   │   ├── input.tsx
│   │   │   ├── label.tsx
│   │   │   ├── select.tsx
│   │   │   ├── skeleton.tsx
│   │   │   ├── table.tsx
│   │   │   └── toast.tsx
│   │   ├── data-table/          # Reusable data table components
│   │   │   ├── data-table.tsx   # Main DataTable component
│   │   │   ├── data-table-pagination.tsx
│   │   │   ├── data-table-column-header.tsx
│   │   │   └── data-table-toolbar.tsx
│   │   ├── charts/
│   │   │   ├── time-series-chart.tsx
│   │   │   ├── kpi-card.tsx
│   │   │   └── metric-bar-chart.tsx
│   │   ├── chat/                # Agent chat (Phase 2 - after INITIAL-10)
│   │   │   ├── chat-message.tsx
│   │   │   ├── chat-input.tsx
│   │   │   └── citation-list.tsx
│   │   ├── layout/
│   │   │   ├── app-layout.tsx   # Main layout with sidebar
│   │   │   ├── sidebar.tsx
│   │   │   ├── header.tsx
│   │   │   └── theme-toggle.tsx
│   │   └── error-boundary.tsx
│   ├── hooks/
│   │   ├── use-stores.ts        # TanStack Query hooks for /dimensions/stores
│   │   ├── use-products.ts      # TanStack Query hooks for /dimensions/products
│   │   ├── use-kpis.ts          # TanStack Query hook for /analytics/kpis
│   │   ├── use-drilldowns.ts    # TanStack Query hook for /analytics/drilldowns
│   │   ├── use-runs.ts          # TanStack Query hooks for /registry/runs
│   │   ├── use-aliases.ts       # TanStack Query hooks for /registry/aliases
│   │   ├── use-jobs.ts          # TanStack Query hooks for /jobs
│   │   └── use-websocket.ts     # WebSocket hook for agent streaming
│   ├── lib/
│   │   ├── api.ts               # Axios/fetch client with base URL
│   │   ├── query-client.ts      # TanStack Query client config
│   │   └── utils.ts             # cn() for class merging (shadcn pattern)
│   ├── pages/
│   │   ├── dashboard.tsx
│   │   ├── explorer/
│   │   │   ├── sales.tsx
│   │   │   ├── stores.tsx
│   │   │   ├── products.tsx
│   │   │   ├── runs.tsx
│   │   │   └── jobs.tsx
│   │   ├── visualize/
│   │   │   ├── forecast.tsx
│   │   │   └── backtest.tsx
│   │   ├── chat.tsx             # Phase 2 - after INITIAL-10
│   │   └── admin.tsx
│   ├── types/
│   │   ├── api.ts               # TypeScript types matching backend schemas
│   │   └── index.ts
│   ├── App.tsx                  # Main app with router
│   ├── main.tsx                 # Entry point
│   └── index.css                # Tailwind imports
├── .env.example                 # VITE_API_BASE_URL, VITE_WS_URL
├── .gitignore
├── components.json              # shadcn/ui config
├── eslint.config.js
├── index.html
├── package.json
├── postcss.config.js
├── tailwind.config.ts
├── tsconfig.json
├── tsconfig.node.json
└── vite.config.ts

examples/ui/
└── README.md                    # Dashboard page map and setup instructions
```

### Known Gotchas & Library Quirks

```typescript
// CRITICAL: shadcn/ui installation command
// Use: npx shadcn@latest init
// NOT: npx shadcn-ui init (deprecated)

// CRITICAL: TanStack Table v8 breaking changes
// - useReactTable (NOT useTable)
// - getCoreRowModel() required
// - manualPagination, manualSorting, manualFiltering for server-side

// CRITICAL: Vite environment variables
// - Must prefix with VITE_ (e.g., VITE_API_BASE_URL)
// - Access via import.meta.env.VITE_API_BASE_URL
// - NOT process.env (that's Node.js)

// CRITICAL: TanStack Query v5
// - queryKey is now an array: ['runs', params]
// - useQuery returns object with { data, isLoading, error }
// - placeholderData replaces keepPreviousData option

// CRITICAL: Recharts responsive container
// - ResponsiveContainer requires explicit parent height
// - Use CSS: min-height: 400px on parent

// CRITICAL: WebSocket reconnection
// - Browser WebSocket API has no auto-reconnect
// - Must implement exponential backoff manually

// CRITICAL: shadcn/ui dark mode
// - Requires ThemeProvider wrapper
// - Uses localStorage for persistence
// - HTML class="dark" toggling

// CRITICAL: Decimal handling from backend
// - Backend sends Decimal as string (e.g., "1234.56")
// - Parse with parseFloat() or use library like decimal.js
// - Format with Intl.NumberFormat for currency display
```

---

## Implementation Blueprint

### Phase 1: Project Scaffolding (Tasks 1-5)

#### Task 1: Initialize Vite + React 19 + TypeScript Project

```bash
# Commands to run (in project root)
cd /path/to/ForecastLabAI
pnpm create vite@latest frontend -- --template react-ts
cd frontend
pnpm install
```

Configure TypeScript strict mode in `tsconfig.json`:
```json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitReturns": true,
    "strictNullChecks": true
  }
}
```

#### Task 2: Install Tailwind CSS 4

```bash
pnpm add -D tailwindcss @tailwindcss/vite
```

Update `vite.config.ts`:
```typescript
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
})
```

Create `src/index.css`:
```css
@import "tailwindcss";
```

#### Task 3: Initialize shadcn/ui

```bash
npx shadcn@latest init
# Choose:
# - Style: Default
# - Base color: Neutral
# - CSS variables: Yes
```

Install required components:
```bash
npx shadcn@latest add button card dialog dropdown-menu input label select skeleton table toast
```

#### Task 4: Install TanStack Libraries

```bash
pnpm add @tanstack/react-table @tanstack/react-query
```

Create `src/lib/query-client.ts`:
```typescript
import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})
```

#### Task 5: Install Recharts and React Router

```bash
pnpm add recharts react-router-dom
```

---

### Phase 2: Core Infrastructure (Tasks 6-10)

#### Task 6: Create API Client

File: `src/lib/api.ts`

```typescript
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8123'

interface RequestConfig {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
  params?: Record<string, string | number | undefined>
}

interface ProblemDetail {
  type: string
  title: string
  status: number
  detail: string
  instance?: string
  errors?: Array<{ field: string; message: string; type: string }>
  code?: string
  request_id?: string
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
  const { method = 'GET', body, params } = config

  const url = new URL(`${API_BASE_URL}${endpoint}`)
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined) {
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
  })

  if (!response.ok) {
    const detail = await response.json() as ProblemDetail
    throw new ApiError(detail.detail || response.statusText, response.status, detail)
  }

  return response.json() as Promise<T>
}
```

#### Task 7: Create TypeScript Types (Match Backend Schemas)

File: `src/types/api.ts`

```typescript
// Pagination
export interface PaginationParams {
  page: number
  page_size: number
}

export interface PaginatedResponse<T> {
  total: number
  page: number
  page_size: number
}

// Dimensions
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
  base_price: string | null  // Decimal as string
  base_cost: string | null   // Decimal as string
  created_at: string
  updated_at: string
}

export interface ProductListResponse extends PaginatedResponse<Product> {
  products: Product[]
}

// Analytics
export interface KPIMetrics {
  total_revenue: string    // Decimal as string
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
  revenue_share_pct: string  // Decimal as string
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

// Registry
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

// Jobs
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
```

#### Task 8: Create TanStack Query Hooks

File: `src/hooks/use-stores.ts`

```typescript
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { StoreListResponse } from '@/types/api'

interface UseStoresParams {
  page: number
  pageSize: number
  region?: string
  storeType?: string
  search?: string
}

export function useStores({ page, pageSize, region, storeType, search }: UseStoresParams) {
  return useQuery({
    queryKey: ['stores', { page, pageSize, region, storeType, search }],
    queryFn: () => api<StoreListResponse>('/dimensions/stores', {
      params: {
        page,
        page_size: pageSize,
        region,
        store_type: storeType,
        search,
      },
    }),
    placeholderData: (previousData) => previousData,
  })
}
```

File: `src/hooks/use-runs.ts`

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { RunListResponse, RunCompareResponse, Alias } from '@/types/api'

interface UseRunsParams {
  page: number
  pageSize: number
  modelType?: string
  status?: string
  storeId?: number
  productId?: number
}

export function useRuns({ page, pageSize, modelType, status, storeId, productId }: UseRunsParams) {
  return useQuery({
    queryKey: ['runs', { page, pageSize, modelType, status, storeId, productId }],
    queryFn: () => api<RunListResponse>('/registry/runs', {
      params: {
        page,
        page_size: pageSize,
        model_type: modelType,
        status,
        store_id: storeId,
        product_id: productId,
      },
    }),
    placeholderData: (previousData) => previousData,
  })
}

export function useCompareRuns(runIdA: string, runIdB: string, enabled = false) {
  return useQuery({
    queryKey: ['runs', 'compare', runIdA, runIdB],
    queryFn: () => api<RunCompareResponse>(`/registry/compare/${runIdA}/${runIdB}`),
    enabled,
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
      queryClient.invalidateQueries({ queryKey: ['aliases'] })
    },
  })
}
```

File: `src/hooks/use-jobs.ts`

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { JobListResponse, Job, JobCreate } from '@/types/api'

interface UseJobsParams {
  page: number
  pageSize: number
  jobType?: string
  status?: string
}

export function useJobs({ page, pageSize, jobType, status }: UseJobsParams) {
  return useQuery({
    queryKey: ['jobs', { page, pageSize, jobType, status }],
    queryFn: () => api<JobListResponse>('/jobs', {
      params: {
        page,
        page_size: pageSize,
        job_type: jobType,
        status,
      },
    }),
    placeholderData: (previousData) => previousData,
    refetchInterval: 5000, // Poll every 5 seconds for status updates
  })
}

export function useJob(jobId: string, enabled = true) {
  return useQuery({
    queryKey: ['jobs', jobId],
    queryFn: () => api<Job>(`/jobs/${jobId}`),
    enabled,
    refetchInterval: (query) => {
      // Stop polling when job is complete
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
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })
}

export function useCancelJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (jobId: string) =>
      api<void>(`/jobs/${jobId}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })
}
```

#### Task 9: Create Layout Components

File: `src/components/layout/app-layout.tsx`

```typescript
import { Outlet } from 'react-router-dom'
import { Sidebar } from './sidebar'
import { Header } from './header'

export function AppLayout() {
  return (
    <div className="flex h-screen bg-background">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
```

File: `src/components/layout/sidebar.tsx`

```typescript
import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/utils'
import {
  LayoutDashboard,
  Table2,
  LineChart,
  MessageSquare,
  Settings,
  Store,
  Package,
  FlaskConical,
  ListTodo,
} from 'lucide-react'

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Sales', href: '/explorer/sales', icon: Table2 },
  { name: 'Stores', href: '/explorer/stores', icon: Store },
  { name: 'Products', href: '/explorer/products', icon: Package },
  { name: 'Model Runs', href: '/explorer/runs', icon: FlaskConical },
  { name: 'Jobs', href: '/explorer/jobs', icon: ListTodo },
  { name: 'Forecast', href: '/visualize/forecast', icon: LineChart },
  { name: 'Chat', href: '/chat', icon: MessageSquare },
  { name: 'Admin', href: '/admin', icon: Settings },
]

export function Sidebar() {
  return (
    <aside className="w-64 border-r bg-card">
      <div className="flex h-14 items-center border-b px-4">
        <span className="font-semibold">ForecastLab</span>
      </div>
      <nav className="space-y-1 p-2">
        {navigation.map((item) => (
          <NavLink
            key={item.href}
            to={item.href}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium',
                isActive
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-muted hover:text-foreground'
              )
            }
          >
            <item.icon className="h-4 w-4" />
            {item.name}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
```

#### Task 10: Create Error Boundary

File: `src/components/error-boundary.tsx`

```typescript
import { Component, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from '@/components/ui/card'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      return (
        <Card className="max-w-md mx-auto mt-8">
          <CardHeader>
            <CardTitle className="text-destructive">Something went wrong</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              {this.state.error?.message || 'An unexpected error occurred'}
            </p>
          </CardContent>
          <CardFooter>
            <Button onClick={() => window.location.reload()}>
              Reload Page
            </Button>
          </CardFooter>
        </Card>
      )
    }

    return this.props.children
  }
}
```

---

### Phase 3: Data Table Components (Tasks 11-15)

#### Task 11: Create Reusable DataTable Component

File: `src/components/data-table/data-table.tsx`

```typescript
import {
  type ColumnDef,
  type PaginationState,
  type SortingState,
  type ColumnFiltersState,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { DataTablePagination } from './data-table-pagination'
import { Skeleton } from '@/components/ui/skeleton'

interface DataTableProps<TData, TValue> {
  columns: ColumnDef<TData, TValue>[]
  data: TData[]
  pageCount: number
  pagination: PaginationState
  onPaginationChange: (updater: PaginationState | ((old: PaginationState) => PaginationState)) => void
  sorting?: SortingState
  onSortingChange?: (updater: SortingState | ((old: SortingState) => SortingState)) => void
  isLoading?: boolean
}

export function DataTable<TData, TValue>({
  columns,
  data,
  pageCount,
  pagination,
  onPaginationChange,
  sorting,
  onSortingChange,
  isLoading = false,
}: DataTableProps<TData, TValue>) {
  const table = useReactTable({
    data,
    columns,
    pageCount,
    state: {
      pagination,
      sorting,
    },
    onPaginationChange,
    onSortingChange,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
  })

  return (
    <div className="space-y-4">
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead key={header.id}>
                    {header.isPlaceholder
                      ? null
                      : flexRender(header.column.columnDef.header, header.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: pagination.pageSize }).map((_, i) => (
                <TableRow key={i}>
                  {columns.map((_, j) => (
                    <TableCell key={j}>
                      <Skeleton className="h-4 w-full" />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : table.getRowModel().rows?.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id}>
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={columns.length} className="h-24 text-center">
                  No results.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      <DataTablePagination table={table} />
    </div>
  )
}
```

#### Task 12: Create Stores Explorer Page

File: `src/pages/explorer/stores.tsx`

```typescript
import { useState } from 'react'
import { type ColumnDef, type PaginationState } from '@tanstack/react-table'
import { DataTable } from '@/components/data-table/data-table'
import { useStores } from '@/hooks/use-stores'
import { Input } from '@/components/ui/input'
import type { Store } from '@/types/api'

const columns: ColumnDef<Store>[] = [
  { accessorKey: 'id', header: 'ID' },
  { accessorKey: 'code', header: 'Code' },
  { accessorKey: 'name', header: 'Name' },
  { accessorKey: 'region', header: 'Region' },
  { accessorKey: 'city', header: 'City' },
  { accessorKey: 'store_type', header: 'Type' },
]

export default function StoresPage() {
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 20,
  })
  const [search, setSearch] = useState('')

  const { data, isLoading } = useStores({
    page: pagination.pageIndex + 1,
    pageSize: pagination.pageSize,
    search: search || undefined,
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Stores</h1>
        <Input
          placeholder="Search stores..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-sm"
        />
      </div>
      <DataTable
        columns={columns}
        data={data?.stores ?? []}
        pageCount={data ? Math.ceil(data.total / data.page_size) : 0}
        pagination={pagination}
        onPaginationChange={setPagination}
        isLoading={isLoading}
      />
    </div>
  )
}
```

#### Task 13: Create Runs Explorer Page

File: `src/pages/explorer/runs.tsx`

```typescript
import { useState } from 'react'
import { type ColumnDef, type PaginationState } from '@tanstack/react-table'
import { DataTable } from '@/components/data-table/data-table'
import { useRuns, useCompareRuns } from '@/hooks/use-runs'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import type { ModelRun, RunStatus } from '@/types/api'

const statusColors: Record<RunStatus, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  running: 'bg-blue-100 text-blue-800',
  success: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
  archived: 'bg-gray-100 text-gray-800',
}

const columns: ColumnDef<ModelRun>[] = [
  {
    id: 'select',
    header: ({ table }) => (
      <Checkbox
        checked={table.getIsAllPageRowsSelected()}
        onCheckedChange={(value) => table.toggleAllPageRowsSelected(!!value)}
      />
    ),
    cell: ({ row }) => (
      <Checkbox
        checked={row.getIsSelected()}
        onCheckedChange={(value) => row.toggleSelected(!!value)}
      />
    ),
  },
  { accessorKey: 'run_id', header: 'Run ID', cell: ({ row }) => row.original.run_id.slice(0, 8) },
  { accessorKey: 'model_type', header: 'Model' },
  {
    accessorKey: 'status',
    header: 'Status',
    cell: ({ row }) => (
      <Badge className={statusColors[row.original.status]}>{row.original.status}</Badge>
    ),
  },
  {
    accessorKey: 'metrics.mae',
    header: 'MAE',
    cell: ({ row }) => row.original.metrics?.mae?.toFixed(2) ?? '-',
  },
  {
    accessorKey: 'metrics.smape',
    header: 'sMAPE',
    cell: ({ row }) => row.original.metrics?.smape ? `${row.original.metrics.smape.toFixed(1)}%` : '-',
  },
  {
    accessorKey: 'created_at',
    header: 'Created',
    cell: ({ row }) => new Date(row.original.created_at).toLocaleDateString(),
  },
]

export default function RunsPage() {
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 20,
  })
  const [selectedRuns, setSelectedRuns] = useState<string[]>([])

  const { data, isLoading } = useRuns({
    page: pagination.pageIndex + 1,
    pageSize: pagination.pageSize,
  })

  const canCompare = selectedRuns.length === 2
  const { data: comparison, refetch: compare } = useCompareRuns(
    selectedRuns[0] || '',
    selectedRuns[1] || '',
    canCompare
  )

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Model Runs</h1>
        <Button
          disabled={!canCompare}
          onClick={() => compare()}
        >
          Compare Selected ({selectedRuns.length}/2)
        </Button>
      </div>
      <DataTable
        columns={columns}
        data={data?.runs ?? []}
        pageCount={data ? Math.ceil(data.total / data.page_size) : 0}
        pagination={pagination}
        onPaginationChange={setPagination}
        isLoading={isLoading}
      />
    </div>
  )
}
```

#### Task 14: Create Jobs Monitor Page

File: `src/pages/explorer/jobs.tsx`

```typescript
import { useState } from 'react'
import { type ColumnDef, type PaginationState } from '@tanstack/react-table'
import { DataTable } from '@/components/data-table/data-table'
import { useJobs, useCancelJob } from '@/hooks/use-jobs'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import type { Job, JobStatus } from '@/types/api'

const statusColors: Record<JobStatus, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  running: 'bg-blue-100 text-blue-800',
  completed: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
  cancelled: 'bg-gray-100 text-gray-800',
}

export default function JobsPage() {
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 20,
  })

  const { data, isLoading } = useJobs({
    page: pagination.pageIndex + 1,
    pageSize: pagination.pageSize,
  })

  const cancelJob = useCancelJob()

  const columns: ColumnDef<Job>[] = [
    { accessorKey: 'job_id', header: 'Job ID', cell: ({ row }) => row.original.job_id.slice(0, 8) },
    { accessorKey: 'job_type', header: 'Type' },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ row }) => (
        <Badge className={statusColors[row.original.status]}>{row.original.status}</Badge>
      ),
    },
    {
      accessorKey: 'created_at',
      header: 'Created',
      cell: ({ row }) => new Date(row.original.created_at).toLocaleString(),
    },
    {
      id: 'actions',
      cell: ({ row }) => {
        if (row.original.status !== 'pending') return null
        return (
          <Button
            variant="destructive"
            size="sm"
            onClick={() => cancelJob.mutate(row.original.job_id)}
          >
            Cancel
          </Button>
        )
      },
    },
  ]

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Jobs</h1>
      <DataTable
        columns={columns}
        data={data?.jobs ?? []}
        pageCount={data ? Math.ceil(data.total / data.page_size) : 0}
        pagination={pagination}
        onPaginationChange={setPagination}
        isLoading={isLoading}
      />
    </div>
  )
}
```

#### Task 15: Create Dashboard Page with KPI Cards

File: `src/pages/dashboard.tsx`

```typescript
import { useState } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { useKPIs } from '@/hooks/use-kpis'
import { Skeleton } from '@/components/ui/skeleton'

function formatCurrency(value: string | null): string {
  if (!value) return '-'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(parseFloat(value))
}

function formatNumber(value: number | null): string {
  if (value === null) return '-'
  return new Intl.NumberFormat('en-US').format(value)
}

export default function DashboardPage() {
  const [dateRange] = useState({
    startDate: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
    endDate: new Date().toISOString().split('T')[0],
  })

  const { data, isLoading } = useKPIs({
    startDate: dateRange.startDate,
    endDate: dateRange.endDate,
  })

  const kpiCards = [
    { title: 'Total Revenue', value: formatCurrency(data?.metrics.total_revenue ?? null) },
    { title: 'Total Units', value: formatNumber(data?.metrics.total_units ?? null) },
    { title: 'Transactions', value: formatNumber(data?.metrics.total_transactions ?? null) },
    { title: 'Avg Unit Price', value: formatCurrency(data?.metrics.avg_unit_price ?? null) },
  ]

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {kpiCards.map((card) => (
          <Card key={card.title}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {card.title}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <Skeleton className="h-8 w-24" />
              ) : (
                <div className="text-2xl font-bold">{card.value}</div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
```

---

### Phase 4: Visualization Components (Tasks 16-18)

#### Task 16: Create Time Series Chart Component

File: `src/components/charts/time-series-chart.tsx`

```typescript
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Area,
  ComposedChart,
} from 'recharts'

interface DataPoint {
  date: string
  actual?: number
  predicted?: number
  lower_bound?: number
  upper_bound?: number
}

interface TimeSeriesChartProps {
  data: DataPoint[]
  showConfidence?: boolean
  height?: number
}

export function TimeSeriesChart({
  data,
  showConfidence = false,
  height = 400,
}: TimeSeriesChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 12 }}
          tickFormatter={(value) => new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
        />
        <YAxis tick={{ fontSize: 12 }} />
        <Tooltip
          contentStyle={{ backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))' }}
          labelFormatter={(value) => new Date(value).toLocaleDateString()}
        />
        <Legend />

        {showConfidence && (
          <Area
            type="monotone"
            dataKey="upper_bound"
            stroke="none"
            fill="hsl(var(--primary))"
            fillOpacity={0.1}
            name="Confidence"
          />
        )}

        <Line
          type="monotone"
          dataKey="actual"
          stroke="hsl(var(--primary))"
          strokeWidth={2}
          dot={false}
          name="Actual"
        />

        <Line
          type="monotone"
          dataKey="predicted"
          stroke="hsl(var(--chart-2))"
          strokeWidth={2}
          strokeDasharray="5 5"
          dot={false}
          name="Predicted"
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
```

#### Task 17: Create Forecast Visualization Page

File: `src/pages/visualize/forecast.tsx`

```typescript
import { useState } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { TimeSeriesChart } from '@/components/charts/time-series-chart'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useStores } from '@/hooks/use-stores'
import { useProducts } from '@/hooks/use-products'

export default function ForecastPage() {
  const [storeId, setStoreId] = useState<string>('')
  const [productId, setProductId] = useState<string>('')

  const { data: stores } = useStores({ page: 1, pageSize: 100 })
  const { data: products } = useProducts({ page: 1, pageSize: 100 })

  // Placeholder data - in production, fetch from job results
  const chartData = [
    { date: '2026-01-01', actual: 100, predicted: 98 },
    { date: '2026-01-02', actual: 120, predicted: 115 },
    { date: '2026-01-03', actual: 110, predicted: 112 },
    { date: '2026-01-04', actual: 140, predicted: 135 },
    { date: '2026-01-05', actual: 130, predicted: 128 },
  ]

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Forecast Visualization</h1>

      <div className="flex gap-4">
        <Select value={storeId} onValueChange={setStoreId}>
          <SelectTrigger className="w-48">
            <SelectValue placeholder="Select store" />
          </SelectTrigger>
          <SelectContent>
            {stores?.stores.map((store) => (
              <SelectItem key={store.id} value={String(store.id)}>
                {store.code} - {store.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={productId} onValueChange={setProductId}>
          <SelectTrigger className="w-48">
            <SelectValue placeholder="Select product" />
          </SelectTrigger>
          <SelectContent>
            {products?.products.map((product) => (
              <SelectItem key={product.id} value={String(product.id)}>
                {product.sku} - {product.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Actual vs Predicted</CardTitle>
        </CardHeader>
        <CardContent className="h-[400px]">
          <TimeSeriesChart data={chartData} showConfidence />
        </CardContent>
      </Card>
    </div>
  )
}
```

#### Task 18: Create Main App Router

File: `src/App.tsx`

```typescript
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from '@/lib/query-client'
import { ThemeProvider } from '@/components/theme-provider'
import { AppLayout } from '@/components/layout/app-layout'
import { ErrorBoundary } from '@/components/error-boundary'

// Pages
import DashboardPage from '@/pages/dashboard'
import StoresPage from '@/pages/explorer/stores'
import ProductsPage from '@/pages/explorer/products'
import RunsPage from '@/pages/explorer/runs'
import JobsPage from '@/pages/explorer/jobs'
import ForecastPage from '@/pages/visualize/forecast'

export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider defaultTheme="system" storageKey="forecastlab-theme">
          <BrowserRouter>
            <Routes>
              <Route element={<AppLayout />}>
                <Route path="/" element={<DashboardPage />} />
                <Route path="/explorer/stores" element={<StoresPage />} />
                <Route path="/explorer/products" element={<ProductsPage />} />
                <Route path="/explorer/runs" element={<RunsPage />} />
                <Route path="/explorer/jobs" element={<JobsPage />} />
                <Route path="/visualize/forecast" element={<ForecastPage />} />
              </Route>
            </Routes>
          </BrowserRouter>
        </ThemeProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
```

---

### Phase 5: Agent Chat (Tasks 19-21) - DEPENDS ON INITIAL-10

#### Task 19: Create WebSocket Hook

File: `src/hooks/use-websocket.ts`

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

  const connect = useCallback(() => {
    if (!url) return

    setStatus('connecting')
    const ws = new WebSocket(url)

    ws.onopen = () => {
      setStatus('connected')
      reconnectCountRef.current = 0
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
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
      if (reconnectCountRef.current < reconnectAttempts) {
        reconnectCountRef.current++
        setTimeout(connect, reconnectInterval)
      }
    }

    wsRef.current = ws
  }, [url, onMessage, onError, reconnectAttempts, reconnectInterval])

  const disconnect = useCallback(() => {
    reconnectCountRef.current = reconnectAttempts // Prevent auto-reconnect
    wsRef.current?.close()
    wsRef.current = null
  }, [reconnectAttempts])

  const send = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof data === 'string' ? data : JSON.stringify(data))
    }
  }, [])

  useEffect(() => {
    connect()
    return () => disconnect()
  }, [connect, disconnect])

  return { status, send, disconnect, reconnect: connect }
}
```

#### Task 20: Create Chat Message Component

File: `src/components/chat/chat-message.tsx`

```typescript
import { cn } from '@/lib/utils'
import { Card } from '@/components/ui/card'

interface Citation {
  source_type: string
  source_id: string
  chunk_id: string
  snippet: string
}

interface ToolCall {
  name: string
  arguments: Record<string, unknown>
  result?: unknown
}

interface ChatMessageProps {
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  toolCalls?: ToolCall[]
  isStreaming?: boolean
}

export function ChatMessage({
  role,
  content,
  citations,
  toolCalls,
  isStreaming,
}: ChatMessageProps) {
  return (
    <div className={cn('flex', role === 'user' ? 'justify-end' : 'justify-start')}>
      <Card className={cn(
        'max-w-[80%] p-4',
        role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted'
      )}>
        <div className="prose prose-sm dark:prose-invert">
          {content}
          {isStreaming && <span className="animate-pulse ml-1">|</span>}
        </div>

        {citations && citations.length > 0 && (
          <div className="mt-4 pt-4 border-t">
            <p className="text-xs font-medium mb-2">Sources:</p>
            <ul className="text-xs space-y-1">
              {citations.map((citation, i) => (
                <li key={i} className="text-muted-foreground">
                  [{i + 1}] {citation.source_id}
                </li>
              ))}
            </ul>
          </div>
        )}

        {toolCalls && toolCalls.length > 0 && (
          <details className="mt-4 pt-4 border-t text-xs">
            <summary className="cursor-pointer font-medium">Tool Calls ({toolCalls.length})</summary>
            <div className="mt-2 space-y-2">
              {toolCalls.map((call, i) => (
                <div key={i} className="bg-background/50 rounded p-2">
                  <code>{call.name}</code>
                </div>
              ))}
            </div>
          </details>
        )}
      </Card>
    </div>
  )
}
```

#### Task 21: Create Chat Page

File: `src/pages/chat.tsx`

```typescript
import { useState, useCallback } from 'react'
import { useWebSocket } from '@/hooks/use-websocket'
import { ChatMessage } from '@/components/chat/chat-message'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card } from '@/components/ui/card'
import { Send } from 'lucide-react'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations?: Array<{ source_type: string; source_id: string; chunk_id: string; snippet: string }>
  toolCalls?: Array<{ name: string; arguments: Record<string, unknown>; result?: unknown }>
  isStreaming?: boolean
}

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8123/agents/stream'

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [streamingContent, setStreamingContent] = useState('')

  const handleMessage = useCallback((data: unknown) => {
    const msg = data as { type: string; content?: string; done?: boolean; citations?: Message['citations']; tool_calls?: Message['toolCalls'] }

    if (msg.type === 'token') {
      setStreamingContent((prev) => prev + (msg.content || ''))
    } else if (msg.type === 'done') {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: streamingContent,
          citations: msg.citations,
          toolCalls: msg.tool_calls,
        },
      ])
      setStreamingContent('')
    }
  }, [streamingContent])

  const { status, send } = useWebSocket(WS_URL, { onMessage: handleMessage })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim()) return

    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: 'user', content: input },
    ])

    send({
      type: 'query',
      agent: 'rag_assistant',
      payload: { query: input },
    })

    setInput('')
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col">
      <h1 className="text-2xl font-bold mb-4">ForecastLab Assistant</h1>

      <Card className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg) => (
          <ChatMessage
            key={msg.id}
            role={msg.role}
            content={msg.content}
            citations={msg.citations}
            toolCalls={msg.toolCalls}
          />
        ))}
        {streamingContent && (
          <ChatMessage role="assistant" content={streamingContent} isStreaming />
        )}
      </Card>

      <form onSubmit={handleSubmit} className="mt-4 flex gap-2">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about forecasting, backtesting, or data..."
          disabled={status !== 'connected'}
        />
        <Button type="submit" disabled={status !== 'connected'}>
          <Send className="h-4 w-4" />
        </Button>
      </form>

      <p className="text-xs text-muted-foreground mt-2">
        Status: {status}
      </p>
    </div>
  )
}
```

---

### Phase 6: Admin Panel & Polish (Tasks 22-24)

#### Task 22: Create Admin Page

File: `src/pages/admin.tsx`

```typescript
import { useAliases, useCreateAlias } from '@/hooks/use-runs'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

export default function AdminPage() {
  const { data: aliases, isLoading } = useAliases()

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Admin Panel</h1>

      <Card>
        <CardHeader>
          <CardTitle>Deployment Aliases</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Alias Name</TableHead>
                <TableHead>Run ID</TableHead>
                <TableHead>Model Type</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center">Loading...</TableCell>
                </TableRow>
              ) : aliases?.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center">No aliases configured</TableCell>
                </TableRow>
              ) : (
                aliases?.map((alias) => (
                  <TableRow key={alias.alias_name}>
                    <TableCell className="font-mono">{alias.alias_name}</TableCell>
                    <TableCell className="font-mono">{alias.run_id.slice(0, 8)}</TableCell>
                    <TableCell>{alias.model_type}</TableCell>
                    <TableCell>
                      <Badge variant={alias.run_status === 'success' ? 'default' : 'secondary'}>
                        {alias.run_status}
                      </Badge>
                    </TableCell>
                    <TableCell>{new Date(alias.created_at).toLocaleDateString()}</TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
```

#### Task 23: Create Environment Configuration

File: `frontend/.env.example`

```env
# API Configuration
VITE_API_BASE_URL=http://localhost:8123
VITE_WS_URL=ws://localhost:8123/agents/stream

# Feature Flags
VITE_ENABLE_AGENT_CHAT=true
VITE_ENABLE_ADMIN_PANEL=true

# Visualization
VITE_DEFAULT_PAGE_SIZE=25
VITE_MAX_CHART_POINTS=365
```

#### Task 24: Create Examples Documentation

File: `examples/ui/README.md`

```markdown
# ForecastLab Dashboard

## Page Map

| Page | Route | API Endpoints | Description |
|------|-------|---------------|-------------|
| Dashboard | `/` | `GET /analytics/kpis` | KPI summary cards |
| Stores | `/explorer/stores` | `GET /dimensions/stores` | Store dimension table |
| Products | `/explorer/products` | `GET /dimensions/products` | Product dimension table |
| Model Runs | `/explorer/runs` | `GET /registry/runs` | Model run leaderboard |
| Jobs | `/explorer/jobs` | `GET /jobs` | Job status monitor |
| Forecast | `/visualize/forecast` | Job results | Forecast visualization |
| Chat | `/chat` | `WS /agents/stream` | Agent chat interface |
| Admin | `/admin` | `GET /registry/aliases` | Admin panel |

## Running the Dashboard

### Prerequisites
- Node.js 20+
- pnpm (recommended) or npm
- Backend running on port 8123

### Development

```bash
cd frontend
pnpm install
pnpm dev
```

Open http://localhost:5173

### Production Build

```bash
cd frontend
pnpm build
pnpm preview
```

## Environment Variables

Copy `.env.example` to `.env` and configure:

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_BASE_URL` | `http://localhost:8123` | Backend API base URL |
| `VITE_WS_URL` | `ws://localhost:8123/agents/stream` | WebSocket URL for chat |

## Tech Stack

- React 19 + TypeScript
- Vite for bundling
- shadcn/ui components
- TanStack Table for data grids
- TanStack Query for data fetching
- Recharts for visualization
- Tailwind CSS 4 for styling
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
cd frontend

# TypeScript compilation
pnpm tsc --noEmit

# ESLint
pnpm eslint src/

# Expected: No errors
```

### Level 2: Build Validation

```bash
cd frontend

# Development build
pnpm dev  # Should start without errors

# Production build
pnpm build

# Expected: Build completes, outputs to dist/
```

### Level 3: Integration Test

```bash
# 1. Start backend
docker-compose up -d
uv run uvicorn app.main:app --port 8123

# 2. Start frontend
cd frontend && pnpm dev

# 3. Manual verification:
# - Open http://localhost:5173
# - Navigate to /explorer/stores
# - Verify data loads from API
# - Check pagination works
# - Verify dark mode toggle

# 4. Lighthouse audit (Chrome DevTools)
# - Performance > 90
# - Accessibility > 90
```

---

## Final Validation Checklist

- [ ] Vite project scaffolded with React 19 + TypeScript strict
- [ ] shadcn/ui components installed and working
- [ ] TanStack Table with server-side pagination
- [ ] TanStack Query hooks for all API endpoints
- [ ] Recharts time series visualization
- [ ] WebSocket hook for agent chat (placeholder if INITIAL-10 not ready)
- [ ] Dark/light theme toggle
- [ ] Responsive sidebar navigation
- [ ] Error boundary with retry
- [ ] All TypeScript strict checks pass
- [ ] ESLint passes
- [ ] Production build succeeds
- [ ] Lighthouse performance > 90

---

## Integration Points

```yaml
BACKEND_DEPENDENCY:
  - Requires backend running on VITE_API_BASE_URL
  - Uses /dimensions/*, /analytics/*, /registry/*, /jobs/* endpoints
  - WebSocket requires INITIAL-10 completion for full chat functionality

PHASE_DEPENDENCIES:
  - INITIAL-9 (RAG): Admin panel shows /rag/sources (placeholder if not ready)
  - INITIAL-10 (Agentic): Chat interface uses WS /agents/stream
  - Phase 7 (Serving): All data tables consume serving layer endpoints

FEATURE_FLAGS:
  - VITE_ENABLE_AGENT_CHAT: Gate chat interface until INITIAL-10 ready
  - VITE_ENABLE_ADMIN_PANEL: Gate admin features
```

---

## Anti-Patterns to Avoid

- Do NOT hardcode API URLs - always use `import.meta.env.VITE_API_BASE_URL`
- Do NOT use `process.env` - that's Node.js, use `import.meta.env` for Vite
- Do NOT install `shadcn-ui` package - use `npx shadcn@latest` CLI
- Do NOT use `useTable` - TanStack Table v8 uses `useReactTable`
- Do NOT forget `manualPagination: true` for server-side tables
- Do NOT skip error boundaries - API errors should be caught gracefully
- Do NOT create custom fetch wrappers with Promise.race timeout - use AbortController

---

## Confidence Score Breakdown

| Area | Score | Rationale |
|------|-------|-----------|
| Project Scaffolding | 9/10 | Vite + React well documented |
| shadcn/ui Integration | 8/10 | CLI-based, clear patterns |
| TanStack Table | 8/10 | Server-side examples available |
| TanStack Query | 9/10 | Mature library, clear docs |
| Recharts | 8/10 | Straightforward API |
| WebSocket Chat | 6/10 | Custom implementation needed, depends on INITIAL-10 |
| TypeScript Types | 8/10 | Backend schemas well-defined |
| Overall | **7.5/10** | Chat dependency on INITIAL-10 lowers confidence |

**Note**: Full chat functionality requires INITIAL-10 (Agentic Layer) WebSocket endpoint. Implement chat page with placeholder/disabled state if INITIAL-10 not ready.
