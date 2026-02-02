# Phase 10: Dashboard ("The Face")

**Date Started**: 2026-02-01
**PRP**: [PRP-11A-frontend-setup.md](../../PRPs/PRP-11A-frontend-setup.md)
**INITIAL**: INITIAL-11A.md (Setup), INITIAL-11B.md (Architecture), INITIAL-11C.md (Pages)
**ADR**: [ADR-0002-frontend-architecture-vite-spa-first.md](../ADR/ADR-0002-frontend-architecture-vite-spa-first.md)

---

## Executive Summary

Phase 10 implements the **Dashboard** - the "Face" of ForecastLabAI that provides a modern React-based user interface for data exploration, model management, and agent interaction.

### Phase 10 Sub-Phases

| Sub-Phase | Description | Status |
|-----------|-------------|--------|
| **10A: Setup** | Project scaffolding, dependencies, shadcn/ui | ✅ Completed |
| **10B: Architecture** | App shell, routing, layout, state management | ✅ Completed |
| **10C: Pages** | Dashboard, Explorer, Visualize, Chat, Admin | ✅ Completed |

---

## Phase 10A: Frontend Setup (Completed)

### Key Features

1. **Modern React Stack**
   - React 19 with TypeScript 5.9 (strict mode)
   - Vite 7 for fast builds and hot module replacement
   - Path aliases (`@/`) for clean imports

2. **Tailwind CSS 4**
   - New `@import "tailwindcss"` syntax
   - `@tailwindcss/vite` plugin integration
   - CSS variables for theming

3. **shadcn/ui Component Library**
   - New York style theme with neutral base color
   - 26 pre-installed components
   - Customizable via CSS variables

4. **Data Management**
   - TanStack Query for server state
   - TanStack Table for data grids
   - React Router 7 for navigation

5. **Development Experience**
   - API proxy to backend (`/api` → `localhost:8123`)
   - ESLint with React Refresh support
   - Hot module replacement

### Technology Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| React | 19.2 | UI framework |
| Vite | 7.3 | Build tool and dev server |
| TypeScript | 5.9 | Type safety (strict mode) |
| Tailwind CSS | 4.1 | Utility-first styling |
| shadcn/ui | New York | Component library |
| TanStack Query | 5.90 | Server state management |
| TanStack Table | 8.21 | Data tables |
| React Router | 7.13 | Client-side routing |
| Recharts | 2.15 | Charts and visualizations |
| date-fns | 4.1 | Date utilities |
| lucide-react | 0.563 | Icons |

---

## Deliverables (Phase 10A)

### Directory Structure

```
frontend/
├── public/
│   └── vite.svg                    # Vite default asset
├── src/
│   ├── components/
│   │   └── ui/                     # shadcn/ui components (26 files)
│   │       ├── accordion.tsx
│   │       ├── alert-dialog.tsx
│   │       ├── badge.tsx
│   │       ├── button.tsx
│   │       ├── calendar.tsx
│   │       ├── card.tsx
│   │       ├── chart.tsx
│   │       ├── checkbox.tsx
│   │       ├── collapsible.tsx
│   │       ├── dialog.tsx
│   │       ├── dropdown-menu.tsx
│   │       ├── input.tsx
│   │       ├── navigation-menu.tsx
│   │       ├── pagination.tsx
│   │       ├── popover.tsx
│   │       ├── progress.tsx
│   │       ├── scroll-area.tsx
│   │       ├── select.tsx
│   │       ├── separator.tsx
│   │       ├── sheet.tsx
│   │       ├── skeleton.tsx
│   │       ├── sonner.tsx
│   │       ├── table.tsx
│   │       ├── tabs.tsx
│   │       ├── textarea.tsx
│   │       └── tooltip.tsx
│   ├── lib/
│   │   └── utils.ts                # cn() utility for class merging
│   ├── App.tsx                     # Main app component
│   ├── main.tsx                    # Entry point
│   └── index.css                   # Tailwind + shadcn theme variables
├── .env.example                    # Environment template
├── .gitignore                      # Node.js ignores
├── components.json                 # shadcn/ui configuration
├── eslint.config.js                # ESLint flat config
├── index.html                      # HTML entry point
├── package.json                    # Dependencies
├── pnpm-lock.yaml                  # Lock file
├── tsconfig.json                   # TypeScript config (root)
├── tsconfig.app.json               # App TypeScript config
├── tsconfig.node.json              # Node TypeScript config
└── vite.config.ts                  # Vite + Tailwind + aliases
```

### Configuration Files

#### vite.config.ts

```typescript
import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8123",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
})
```

#### components.json

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "",
    "css": "src/index.css",
    "baseColor": "neutral",
    "cssVariables": true,
    "prefix": ""
  },
  "iconLibrary": "lucide",
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  }
}
```

#### .env.example

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

---

## Commands

```bash
cd frontend

# Install dependencies
pnpm install

# Development server (http://localhost:5173)
pnpm dev

# Production build
pnpm build

# Linting
pnpm lint

# Type checking
pnpm tsc --noEmit

# Preview production build
pnpm preview
```

---

## Validation Results (Phase 10A)

### Build Verification

```bash
pnpm build
```

**Result**: ✅ Build successful

```
vite v7.3.1 building client environment for production...
✓ 36 modules transformed.
dist/index.html                   0.46 kB │ gzip:  0.29 kB
dist/assets/index-DZWA8ABU.css   66.09 kB │ gzip: 10.87 kB
dist/assets/index-CBp0D9dw.js   224.06 kB │ gzip: 70.70 kB
✓ built in 1.32s
```

### TypeScript Check

```bash
pnpm tsc --noEmit
```

**Result**: ✅ 0 errors

### ESLint Check

```bash
pnpm lint
```

**Result**: ✅ No errors (shadcn/ui components excluded from react-refresh rule)

### Component Verification

```bash
ls src/components/ui/ | wc -l
```

**Result**: ✅ 26 component files

---

## Phase 10B: Architecture (Completed)

**Completion Date**: 2026-02-02
**PRP**: [PRP-11B-dashboard-architecture.md](../../PRPs/PRP-11B-dashboard-architecture.md)

### Deliverables

1. **App Shell**
   - Top navigation bar with logo, nav links, and theme toggle
   - Mobile-responsive drawer navigation
   - Outlet-based content area with consistent layout

2. **Routing**
   - React Router 7 with lazy loading for all pages
   - Code-split chunks for optimal loading
   - Nested routes for Explorer and Visualize sections

3. **State Management**
   - TanStack Query for server state with optimized caching
   - Theme context with system preference detection
   - URL-based pagination state

4. **API Client**
   - Typed fetch wrapper (`src/lib/api.ts`)
   - RFC 7807 Problem Details error handling
   - `ApiError` class for structured error handling

5. **TanStack Query Hooks**
   - `useStores`, `useProducts` - Dimension data
   - `useKPIs`, `useDrilldowns` - Analytics data
   - `useRuns`, `useJobs` - Model operations
   - `useRagSources` - RAG management
   - `useWebSocket` - Agent streaming with reconnection

6. **Reusable Components**
   - `DataTable` - Server-side pagination with TanStack Table v8
   - `DataTableToolbar` - Filters and search
   - `StatusBadge` - Status indicators with variants
   - `DateRangePicker` - Date range selection
   - `ErrorDisplay` - Error states with retry
   - `LoadingState` - Loading indicators
   - `KPICard` - Metric display cards
   - `TimeSeriesChart` - Forecast visualizations
   - `BacktestFoldsChart` - Backtest fold results

### Directory Structure (Phase 10B)

```
src/
├── components/
│   ├── charts/                 # Chart components
│   │   ├── kpi-card.tsx
│   │   ├── time-series-chart.tsx
│   │   ├── backtest-folds-chart.tsx
│   │   └── index.ts
│   ├── chat/                   # Agent chat components
│   │   ├── chat-message.tsx
│   │   ├── chat-input.tsx
│   │   ├── tool-call-display.tsx
│   │   └── index.ts
│   ├── common/                 # Shared components
│   │   ├── status-badge.tsx
│   │   ├── date-range-picker.tsx
│   │   ├── error-display.tsx
│   │   ├── loading-state.tsx
│   │   └── index.ts
│   ├── data-table/             # DataTable components
│   │   ├── data-table.tsx
│   │   ├── data-table-pagination.tsx
│   │   ├── data-table-toolbar.tsx
│   │   └── index.ts
│   └── layout/                 # Layout components
│       ├── app-shell.tsx
│       ├── top-nav.tsx
│       ├── theme-toggle.tsx
│       └── index.ts
├── hooks/                      # TanStack Query hooks
│   ├── use-stores.ts
│   ├── use-products.ts
│   ├── use-kpis.ts
│   ├── use-drilldowns.ts
│   ├── use-runs.ts
│   ├── use-jobs.ts
│   ├── use-rag-sources.ts
│   ├── use-websocket.ts
│   └── index.ts
├── lib/
│   ├── api.ts                  # API client
│   ├── query-client.ts         # TanStack Query config
│   ├── constants.ts            # Routes and nav items
│   ├── date-utils.ts           # Date helpers
│   └── status-utils.ts         # Status mapping
├── providers/
│   └── theme-provider.tsx      # Theme context
└── types/
    ├── api.ts                  # API type definitions
    └── index.ts
```

### Build Verification (Phase 10B)

```bash
pnpm build
```

**Result**: ✅ Build successful

```
vite v7.3.1 building client environment for production...
✓ 3470 modules transformed.
dist/index.html                   0.46 kB │ gzip:   0.29 kB
dist/assets/index-[hash].css     79.08 kB │ gzip:  13.16 kB
dist/assets/index-[hash].js     435.43 kB │ gzip: 137.51 kB
✓ built in 7.96s
```

### ESLint Check (Phase 10B)

**Result**: ✅ 0 errors, 1 warning (expected TanStack Table warning)

---

## Phase 10C: Pages (Completed)

**Completion Date**: 2026-02-02
**PRP**: [PRP-11B-dashboard-architecture.md](../../PRPs/PRP-11B-dashboard-architecture.md)

### Implemented Pages

| Page | Route | Description |
|------|-------|-------------|
| Dashboard | `/` | KPI cards, top stores/products by revenue |
| Stores | `/explorer/stores` | Store list with region filter |
| Products | `/explorer/products` | Product catalog with category filter |
| Model Runs | `/explorer/runs` | Run history with model/status filters |
| Jobs | `/explorer/jobs` | Job monitor with cancel action |
| Sales | `/explorer/sales` | Drilldowns by store/product/category/region/date |
| Forecast | `/visualize/forecast` | Time series forecast visualization |
| Backtest | `/visualize/backtest` | Backtest fold metrics and comparison |
| Chat | `/chat` | Agent conversation with tool call display |
| Admin | `/admin` | RAG sources and deployment alias management |

### Page Features

- **Dashboard**: 4 KPI cards, top 5 stores, top 5 products with date range filter
- **Explorer Pages**: Server-side pagination, column filters, reset functionality
- **Jobs Page**: Cancel pending jobs with confirmation dialog
- **Sales Page**: Tab-based dimension switching (store/product/category/region/date)
- **Forecast Page**: Store/product selection, time series chart with actual vs predicted
- **Backtest Page**: Run selection, fold metrics chart, metrics summary card
- **Chat Page**: Message history, tool call visualization, WebSocket streaming
- **Admin Page**: RAG source table, deployment alias table with CRUD operations

### Integration Points with Backend

| Frontend Feature | Backend Endpoint | Status |
|------------------|------------------|--------|
| KPI Cards | `GET /analytics/kpis` | ✅ Ready |
| Data Tables | `GET /dimensions/*` | ✅ Ready |
| Forecast Charts | `POST /forecasting/predict` | ✅ Ready |
| Agent Chat | `WS /agents/stream` | ✅ Ready |
| Model Registry | `GET /registry/runs` | ✅ Ready |
| Backtest Results | `POST /backtesting/run` | ✅ Ready |

---

## Dependencies on Previous Phases

| Phase | Dependency | Status |
|-------|------------|--------|
| Phase 7 | Serving Layer (FastAPI) | ✅ Complete |
| Phase 8 | RAG Knowledge Base | ✅ Complete |
| Phase 9 | Agentic Layer (WebSocket) | ✅ Complete |

---

## Known Limitations

1. **No Tests**: Frontend testing setup deferred to future phase
2. **No Authentication**: Auth UI deferred to future phase
3. **Mock-Ready**: Pages render with mock data patterns; backend integration required

---

## References

- [Vite Documentation](https://vite.dev/guide/)
- [Tailwind CSS 4](https://tailwindcss.com/docs)
- [shadcn/ui Installation](https://ui.shadcn.com/docs/installation/vite)
- [TanStack Query](https://tanstack.com/query/latest)
- [TanStack Table](https://tanstack.com/table/latest)
- [React Router](https://reactrouter.com/)
- [ADR-0002](../ADR/ADR-0002-frontend-architecture-vite-spa-first.md) - Frontend Architecture Decision
- [PRP-11A](../../PRPs/PRP-11A-frontend-setup.md) - Frontend Setup PRP
- [PRP-11B](../../PRPs/PRP-11B-dashboard-architecture.md) - Dashboard Architecture PRP

---

**Phase 10A Completion Date**: 2026-02-01
**Phase 10B Completion Date**: 2026-02-02
**Phase 10C Completion Date**: 2026-02-02
**Phase Status**: ✅ Complete
**Files Changed**: 49 files, 4404 insertions
