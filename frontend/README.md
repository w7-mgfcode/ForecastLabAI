# ForecastLabAI Frontend

React-based dashboard for the ForecastLabAI retail demand forecasting system.

## Tech Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| React | 19.2 | UI framework |
| Vite | 7.3 | Build tool and dev server |
| TypeScript | 5.9 | Type safety (strict mode) |
| Tailwind CSS | 4.1 | Utility-first styling |
| shadcn/ui | New York | Component library |
| TanStack Query | 5.90 | Server state management |
| TanStack Table | 8.21 | Data tables with pagination |
| React Router | 7.13 | Client-side routing |
| Recharts | 2.15 | Charts and visualizations |
| date-fns | 4.1 | Date utilities |

## Quick Start

```bash
# Install dependencies
pnpm install

# Start development server (http://localhost:5173)
pnpm dev

# Build for production
pnpm build

# Lint code
pnpm lint

# Type check
pnpm tsc --noEmit
```

## Project Structure

```
src/
├── components/
│   ├── ui/                   # shadcn/ui primitives (26 components)
│   ├── charts/               # KPI cards, time series, backtest charts
│   ├── chat/                 # Agent chat interface components
│   ├── common/               # StatusBadge, DateRangePicker, ErrorDisplay
│   ├── data-table/           # Server-side paginated DataTable
│   └── layout/               # AppShell, TopNav, ThemeToggle
├── hooks/
│   ├── use-stores.ts         # Store data hooks
│   ├── use-products.ts       # Product data hooks
│   ├── use-kpis.ts           # KPI metrics hooks
│   ├── use-drilldowns.ts     # Sales drilldown hooks
│   ├── use-runs.ts           # Model run hooks
│   ├── use-jobs.ts           # Job monitoring hooks
│   ├── use-rag-sources.ts    # RAG source hooks
│   └── use-websocket.ts      # WebSocket connection hook
├── lib/
│   ├── api.ts                # Typed fetch wrapper with RFC 7807 errors
│   ├── query-client.ts       # TanStack Query configuration
│   ├── constants.ts          # Routes and navigation items
│   ├── date-utils.ts         # Date range helpers
│   ├── status-utils.ts       # Status variant mapping
│   └── utils.ts              # cn() class merging utility
├── pages/
│   ├── dashboard.tsx         # Main dashboard with KPIs
│   ├── chat.tsx              # Agent chat interface
│   ├── admin.tsx             # RAG sources and deployment management
│   ├── explorer/
│   │   ├── stores.tsx        # Store browser
│   │   ├── products.tsx      # Product browser
│   │   ├── runs.tsx          # Model run explorer
│   │   ├── jobs.tsx          # Job monitor
│   │   └── sales.tsx         # Sales drilldown explorer
│   └── visualize/
│       ├── forecast.tsx      # Forecast visualization
│       └── backtest.tsx      # Backtest results visualization
├── providers/
│   └── theme-provider.tsx    # Dark/light mode provider
├── types/
│   └── api.ts                # TypeScript types for all API responses
├── App.tsx                   # Router configuration with lazy loading
├── main.tsx                  # Entry point
└── index.css                 # Tailwind + shadcn theme variables
```

## Routes

| Route | Page | Description |
|-------|------|-------------|
| `/` | Dashboard | KPI cards, top stores/products |
| `/explorer/stores` | Stores | Store list with pagination |
| `/explorer/products` | Products | Product catalog with filters |
| `/explorer/runs` | Model Runs | Model run history |
| `/explorer/jobs` | Jobs | Job queue monitoring |
| `/explorer/sales` | Sales | Sales drilldowns by dimension |
| `/visualize/forecast` | Forecast | Time series forecast charts |
| `/visualize/backtest` | Backtest | Backtest fold results |
| `/chat` | Chat | Agent conversation interface |
| `/admin` | Admin | RAG sources and deployments |

## API Integration

The frontend connects to the FastAPI backend at `http://localhost:8123`. In development, requests to `/api` are proxied to the backend.

### API Client

```typescript
import { api } from '@/lib/api'

// Typed fetch with automatic error handling
const stores = await api.get<PaginatedResponse<Store>>('/dimensions/stores')

// RFC 7807 errors are thrown as ApiError
try {
  await api.post('/registry/runs', payload)
} catch (error) {
  if (error instanceof ApiError) {
    console.log(error.type, error.title, error.detail)
  }
}
```

### TanStack Query Hooks

```typescript
import { useStores } from '@/hooks/use-stores'

function StoreList() {
  const { data, isLoading, error } = useStores({
    page: 1,
    pageSize: 25,
    region: 'West',
  })
  // ...
}
```

## Component Patterns

### DataTable with Server-Side Pagination

```typescript
import { DataTable } from '@/components/data-table'
import { DataTableToolbar } from '@/components/data-table'

<DataTableToolbar
  filters={[{ key: 'status', label: 'Status', options: [...] }]}
  filterValues={filters}
  onFilterChange={handleFilterChange}
/>
<DataTable
  columns={columns}
  data={data?.items ?? []}
  pageCount={pageCount}
  pagination={pagination}
  onPaginationChange={setPagination}
  isLoading={isLoading}
/>
```

### Status Badge

```typescript
import { StatusBadge } from '@/components/common'
import { getStatusVariant } from '@/lib/status-utils'

<StatusBadge variant={getStatusVariant(run.status)}>
  {run.status}
</StatusBadge>
```

### Date Range Picker

```typescript
import { DateRangePicker } from '@/components/common'

<DateRangePicker
  value={dateRange}
  onChange={setDateRange}
  placeholder="Select date range"
/>
```

## Theming

The app uses `next-themes` for dark/light mode with system preference detection. Theme CSS variables are defined in `src/index.css`.

```typescript
import { ThemeToggle } from '@/components/layout'

// Toggle button in navigation
<ThemeToggle />
```

## Environment Variables

Copy `.env.example` to `.env`:

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

## Development

### Adding shadcn/ui Components

```bash
pnpm dlx shadcn@latest add [component-name]
```

### Adding New Pages

1. Create page component in `src/pages/`
2. Add route to `src/App.tsx`
3. Add navigation item to `src/lib/constants.ts`

### Adding New API Hooks

1. Add TypeScript types to `src/types/api.ts`
2. Create hook in `src/hooks/use-[resource].ts`
3. Export from `src/hooks/index.ts`

## Build Output

Production build outputs to `dist/`:

```
dist/
├── index.html                 0.46 kB
├── assets/
│   ├── index-[hash].css      79.08 kB (13.16 kB gzip)
│   └── index-[hash].js      435.43 kB (137.51 kB gzip)
```

Code splitting is enabled via React lazy loading, creating separate chunks for each page.

## References

- [Vite Documentation](https://vite.dev/guide/)
- [Tailwind CSS 4](https://tailwindcss.com/docs)
- [shadcn/ui](https://ui.shadcn.com/)
- [TanStack Query](https://tanstack.com/query/latest)
- [TanStack Table](https://tanstack.com/table/latest)
- [React Router](https://reactrouter.com/)
