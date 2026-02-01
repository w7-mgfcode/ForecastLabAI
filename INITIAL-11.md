# INITIAL-11.md — ForecastLab Dashboard (The Face)

## Architectural Role

**"The Face"** - User interface, data visualization, and agent interaction using React 19 + shadcn/ui.

This phase provides the visual layer for:
- Data exploration with server-side pagination and filtering
- Time series visualization with interactive charts
- Agent chat interface with streaming responses
- Admin panel for system management

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Framework | React 19 + [Vite](https://vite.dev/) | Fast build, HMR |
| Components | [shadcn/ui](https://ui.shadcn.com/) | Accessible, customizable UI |
| Data Tables | [TanStack Table](https://tanstack.com/table/latest) | Server-side data grids |
| Data Fetching | [TanStack Query](https://tanstack.com/query/latest) | Caching, invalidation |
| Charts | [Recharts](https://recharts.org/) | Time series visualization |
| Styling | Tailwind CSS 4 | Utility-first CSS |
| State | React 19 `use()` + TanStack Query | Server state management |

---

## FEATURE

### Data Explorer
Interactive data tables with full server-side capabilities:
- **Tables**: Sales, Stores, Products, Model Runs, Jobs
- **Features**: Pagination, sorting, filtering, column visibility
- **Export**: CSV download for selected/all rows
- **Pattern**: [shadcn/ui Data Table](https://ui.shadcn.com/docs/components/data-table)

### Time Series Visualizers
Charts for forecasting analysis:
- **Actual vs Predicted**: Line chart with confidence intervals
- **Backtest Folds**: Train/test split visualization
- **Metric Comparison**: Bar charts for model comparison
- **Interactive**: Tooltips, zoom, pan, brush selection

### Agent Chat Interface
Real-time interaction with AI agents:
- **Streaming**: WebSocket-based token streaming
- **Citations**: Rendered with source links
- **Tool Calls**: Collapsible visualization of agent actions
- **History**: Session sidebar with conversation threads

### Admin Panel
System management and monitoring:
- **RAG Sources**: Index/delete documentation sources
- **Model Aliases**: Manage deployment aliases
- **Health Dashboard**: Service status, recent errors
- **Job Monitor**: Active and historical job status

---

## PAGE STRUCTURE

### /dashboard
Main dashboard with KPI summary cards and quick actions.

### /explorer/sales
Sales data explorer with date range filtering.

```
┌─────────────────────────────────────────────────────────────┐
│  Sales Explorer                                    [Export] │
├─────────────────────────────────────────────────────────────┤
│  Filters: [Date Range] [Store ▼] [Product ▼] [Search...]    │
├─────────────────────────────────────────────────────────────┤
│  Date        │ Store   │ Product │ Quantity │ Revenue       │
│  2026-01-15  │ S001    │ P001    │ 150      │ $2,250.00     │
│  2026-01-15  │ S001    │ P002    │ 75       │ $1,125.00     │
│  ...         │ ...     │ ...     │ ...      │ ...           │
├─────────────────────────────────────────────────────────────┤
│  Page 1 of 50  │  [< Prev]  [1] [2] [3] ... [50]  [Next >]  │
└─────────────────────────────────────────────────────────────┘
```

### /explorer/runs
Model run explorer with comparison capabilities.

```
┌─────────────────────────────────────────────────────────────┐
│  Model Runs                              [Compare Selected] │
├─────────────────────────────────────────────────────────────┤
│  [☐] │ Run ID    │ Model    │ Status  │ MAE   │ Created     │
│  [☐] │ run_abc   │ MA(14)   │ SUCCESS │ 12.5  │ 2h ago      │
│  [☐] │ run_def   │ SN(7)    │ SUCCESS │ 15.2  │ 3h ago      │
│  [☐] │ run_ghi   │ Naive    │ SUCCESS │ 18.9  │ 5h ago      │
├─────────────────────────────────────────────────────────────┤
│  Showing 3 of 127 runs                                      │
└─────────────────────────────────────────────────────────────┘
```

### /visualize/forecast
Forecast visualization with actual vs predicted overlay.

```
┌─────────────────────────────────────────────────────────────┐
│  Forecast: Store S001, Product P001                         │
├─────────────────────────────────────────────────────────────┤
│  [Store ▼] [Product ▼] [Model Run ▼] [Date Range]          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  200 ─┤                               ╭──────              │
│       │                          ╭────╯    Predicted       │
│  150 ─┤                     ╭────╯                         │
│       │                ╭────╯      ───── Actual            │
│  100 ─┤           ╭────╯           - - - Confidence        │
│       │      ╭────╯                                        │
│   50 ─┤ ╭────╯                                             │
│       │─╯                                                   │
│    0 ─┼────────────────────────────────────────────────    │
│       Jan 1     Jan 15    Feb 1     Feb 15    Mar 1        │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  MAE: 12.5  │  sMAPE: 15.2%  │  WAPE: 8.1%  │  Bias: -2.3  │
└─────────────────────────────────────────────────────────────┘
```

### /visualize/backtest
Backtest fold visualization.

```
┌─────────────────────────────────────────────────────────────┐
│  Backtest: run_abc123 (5-fold Expanding Window)             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Fold 1: ████████████░░░░  MAE: 14.2  sMAPE: 16.8%         │
│  Fold 2: █████████████████░░░░  MAE: 13.1  sMAPE: 15.4%    │
│  Fold 3: ███████████████████████░░░░  MAE: 12.8  sMAPE: 14.9│
│  Fold 4: █████████████████████████████░░░░  MAE: 11.9      │
│  Fold 5: ███████████████████████████████████░░░░  MAE: 11.2│
│                                                             │
│  █ Train   ░ Test                                          │
├─────────────────────────────────────────────────────────────┤
│  Aggregated: MAE: 12.6 ± 1.1  │  Stability: 0.91           │
└─────────────────────────────────────────────────────────────┘
```

### /chat
Agent chat interface with streaming.

```
┌─────────────────────────────────────────────────────────────┐
│  ForecastLab Assistant                                      │
├────────────┬────────────────────────────────────────────────┤
│  Sessions  │                                                │
│  ─────────│  How does backtesting prevent data leakage?    │
│  Today     │                                                │
│  ◉ Current │  The backtesting module prevents data leakage │
│  ○ 10:30am │  through several mechanisms:                   │
│  ○ 9:15am  │                                                │
│  Yesterday │  1. **Time-based splits**: Uses expanding...   │
│  ○ 4:45pm  │                                                │
│            │  📚 Citations:                                  │
│            │  [1] docs/PHASE/5-BACKTESTING.md               │
│            │  [2] CLAUDE.md                                 │
│            │                                                │
│            │  ──────────────────────────────────────────    │
│            │  🔧 Tool: retrieve_context (5 chunks found)    │
│            │  ──────────────────────────────────────────    │
├────────────┴────────────────────────────────────────────────┤
│  [Type your question...]                          [Send ➤] │
└─────────────────────────────────────────────────────────────┘
```

### /admin
Admin panel for system management.

---

## COMPONENTS

### DataTable (shadcn/ui pattern)

```tsx
// components/data-table/data-table.tsx
import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table"

interface DataTableProps<TData, TValue> {
  columns: ColumnDef<TData, TValue>[]
  data: TData[]
  pageCount: number
  pageIndex: number
  pageSize: number
  onPaginationChange: (pagination: PaginationState) => void
  onSortingChange: (sorting: SortingState) => void
  onFilterChange: (filters: ColumnFiltersState) => void
}

export function DataTable<TData, TValue>({
  columns,
  data,
  pageCount,
  ...props
}: DataTableProps<TData, TValue>) {
  const table = useReactTable({
    data,
    columns,
    pageCount,
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    getCoreRowModel: getCoreRowModel(),
    // ...
  })

  return (
    <Table>
      <TableHeader>...</TableHeader>
      <TableBody>...</TableBody>
    </Table>
  )
}
```

### TimeSeriesChart

```tsx
// components/charts/time-series-chart.tsx
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend } from 'recharts'

interface TimeSeriesChartProps {
  data: { date: string; actual: number; predicted?: number }[]
  showConfidence?: boolean
  height?: number
}

export function TimeSeriesChart({ data, showConfidence, height = 400 }: TimeSeriesChartProps) {
  return (
    <LineChart data={data} height={height}>
      <XAxis dataKey="date" />
      <YAxis />
      <Tooltip />
      <Legend />
      <Line type="monotone" dataKey="actual" stroke="#2563eb" name="Actual" />
      {data[0]?.predicted !== undefined && (
        <Line type="monotone" dataKey="predicted" stroke="#16a34a" name="Predicted" strokeDasharray="5 5" />
      )}
    </LineChart>
  )
}
```

### ChatMessage

```tsx
// components/chat/chat-message.tsx
interface ChatMessageProps {
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  toolCalls?: ToolCall[]
  isStreaming?: boolean
}

export function ChatMessage({ role, content, citations, toolCalls, isStreaming }: ChatMessageProps) {
  return (
    <div className={cn("flex", role === 'user' ? 'justify-end' : 'justify-start')}>
      <div className="max-w-[80%] rounded-lg p-4 bg-muted">
        <Markdown>{content}</Markdown>
        {isStreaming && <span className="animate-pulse">▋</span>}
        {citations && <CitationList citations={citations} />}
        {toolCalls && <ToolCallList toolCalls={toolCalls} />}
      </div>
    </div>
  )
}
```

---

## API HOOKS (TanStack Query)

```tsx
// hooks/use-sales.ts
export function useSales(params: SalesQueryParams) {
  return useQuery({
    queryKey: ['sales', params],
    queryFn: () => api.get('/analytics/drilldowns', { params }),
    placeholderData: keepPreviousData,
  })
}

// hooks/use-runs.ts
export function useRuns(params: RunsQueryParams) {
  return useQuery({
    queryKey: ['runs', params],
    queryFn: () => api.get('/registry/runs', { params }),
  })
}

// hooks/use-chat.ts
export function useChat(sessionId?: string) {
  const [messages, setMessages] = useState<Message[]>([])
  const ws = useWebSocket(`${WS_URL}/agents/stream`)

  const sendMessage = useCallback((content: string) => {
    ws.send(JSON.stringify({ type: 'query', agent: 'rag_assistant', payload: { query: content } }))
  }, [ws])

  return { messages, sendMessage, isConnected: ws.readyState === WebSocket.OPEN }
}
```

---

## CONFIGURATION (Environment)

```env
# .env.example for frontend

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

## EXAMPLES

### examples/ui/README.md
```markdown
# Dashboard Page Map

| Page | API Endpoints | Description |
|------|---------------|-------------|
| /dashboard | GET /analytics/kpis | KPI summary cards |
| /explorer/sales | GET /analytics/drilldowns | Sales data table |
| /explorer/runs | GET /registry/runs | Model run table |
| /visualize/forecast | GET /forecasting/predict | Forecast chart |
| /visualize/backtest | GET /backtesting/results/{run_id} | Fold visualization |
| /chat | WS /agents/stream | Agent chat |
| /admin | GET /rag/sources, GET /registry/aliases | Admin panel |

## Running the Dashboard

\`\`\`bash
cd frontend
pnpm install
pnpm dev
\`\`\`

Open http://localhost:5173
```

---

## SUCCESS CRITERIA

- [ ] Data tables handle 10k+ rows with virtual scrolling
- [ ] Server-side pagination, sorting, filtering all functional
- [ ] Charts render smoothly with 365+ data points
- [ ] WebSocket chat shows streaming tokens in real-time
- [ ] Citations render as clickable source links
- [ ] Tool calls displayed in collapsible sections
- [ ] Responsive design works on tablet and mobile
- [ ] Lighthouse performance score > 90
- [ ] Accessibility: keyboard navigation, screen reader support
- [ ] Dark/light theme toggle

---

## CROSS-MODULE INTEGRATION

| Direction | Module | Integration Point |
|-----------|--------|-------------------|
| **← RAG Layer** | INITIAL-9 | Displays indexed sources, allows re-indexing |
| **← Agentic Layer** | INITIAL-10 | Chat interface, experiment status display |
| **← Registry** | Phase 6 | Run leaderboard, comparison views |
| **← Analytics** | Phase 7 | KPI dashboard, drilldown charts |
| **← Jobs** | Phase 7 | Job status monitoring |
| **← Dimensions** | Phase 7 | Store/product selectors |

---

## DOCUMENTATION LINKS

- [shadcn/ui Documentation](https://ui.shadcn.com/)
- [shadcn/ui Data Table](https://ui.shadcn.com/docs/components/data-table)
- [shadcn/ui Table](https://ui.shadcn.com/docs/components/table)
- [TanStack Table](https://tanstack.com/table/latest)
- [TanStack Query](https://tanstack.com/query/latest)
- [Recharts](https://recharts.org/)
- [Vite Documentation](https://vite.dev/)
- [React 19 Documentation](https://react.dev/)
- [Tailwind CSS 4](https://tailwindcss.com/)

---

## OTHER CONSIDERATIONS

- **No Hardcoded URLs**: API base URL from environment variable only
- **Error Boundaries**: Graceful error handling with retry options
- **Loading States**: Skeleton components for all async data
- **Optimistic Updates**: Instant UI feedback for mutations
- **Caching**: TanStack Query manages cache invalidation
- **Bundle Size**: Code splitting per route for fast initial load
