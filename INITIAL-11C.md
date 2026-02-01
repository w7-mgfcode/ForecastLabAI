# INITIAL-11C.md — ForecastLab Dashboard (The Face)

> **Part C of 3**: Components, Hooks, Configuration, Success Criteria, Integration, and Considerations
> See also: [INITIAL-11A.md](./INITIAL-11A.md) (Overview, Tech Stack) | [INITIAL-11B.md](./INITIAL-11B.md) (Page Structure)

---

## COMPONENTS

### DataTable (shadcn/ui pattern)

Uses the official [shadcn/ui Data Table pattern](https://ui.shadcn.com/docs/components/data-table) with TanStack Table for server-side operations.

```tsx
// components/data-table/data-table.tsx
"use client"

import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
  type PaginationState,
  type SortingState,
  type ColumnFiltersState,
} from "@tanstack/react-table"

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"

interface DataTableProps<TData, TValue> {
  columns: ColumnDef<TData, TValue>[]
  data: TData[]
  pageCount: number
  pagination: PaginationState
  onPaginationChange: (pagination: PaginationState) => void
  sorting?: SortingState
  onSortingChange?: (sorting: SortingState) => void
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
  isLoading,
}: DataTableProps<TData, TValue>) {
  const table = useReactTable({
    data,
    columns,
    pageCount,
    state: { pagination, sorting },
    onPaginationChange: (updater) => {
      const next = typeof updater === "function" ? updater(pagination) : updater
      onPaginationChange(next)
    },
    onSortingChange: (updater) => {
      if (!onSortingChange || !sorting) return
      const next = typeof updater === "function" ? updater(sorting) : updater
      onSortingChange(next)
    },
    manualPagination: true,
    manualSorting: true,
    getCoreRowModel: getCoreRowModel(),
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
                    <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
                  ))}
                </TableRow>
              ))
            ) : table.getRowModel().rows?.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id} data-state={row.getIsSelected() && "selected"}>
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
      <div className="flex items-center justify-end space-x-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => table.previousPage()}
          disabled={!table.getCanPreviousPage()}
        >
          Previous
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => table.nextPage()}
          disabled={!table.getCanNextPage()}
        >
          Next
        </Button>
      </div>
    </div>
  )
}
```

**Required shadcn components:** `table`, `button`, `skeleton`
**Add command:** `npx shadcn@latest add table button skeleton`

---

### TimeSeriesChart

Uses shadcn/ui `chart` component which wraps Recharts with consistent theming.

```tsx
// components/charts/time-series-chart.tsx
"use client"

import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import { Badge } from "@/components/ui/badge"

interface TimeSeriesChartProps {
  title: string
  description?: string
  data: { date: string; actual: number; predicted?: number }[]
  metrics?: { mae?: number; smape?: number; wape?: number; bias?: number }
  height?: number
}

const chartConfig = {
  actual: {
    label: "Actual",
    color: "var(--chart-1)",
  },
  predicted: {
    label: "Predicted",
    color: "var(--chart-2)",
  },
} satisfies ChartConfig

export function TimeSeriesChart({
  title,
  description,
  data,
  metrics,
  height = 350,
}: TimeSeriesChartProps) {
  const hasPredicted = data.some((d) => d.predicted !== undefined)

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>
        <ChartContainer config={chartConfig} className={`h-[${height}px] w-full`}>
          <LineChart data={data} margin={{ left: 12, right: 12 }}>
            <CartesianGrid vertical={false} />
            <XAxis
              dataKey="date"
              tickLine={false}
              axisLine={false}
              tickMargin={8}
              tickFormatter={(value) => new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
            />
            <YAxis tickLine={false} axisLine={false} tickMargin={8} />
            <ChartTooltip cursor={false} content={<ChartTooltipContent />} />
            <Line
              dataKey="actual"
              type="monotone"
              stroke="var(--color-actual)"
              strokeWidth={2}
              dot={false}
            />
            {hasPredicted && (
              <Line
                dataKey="predicted"
                type="monotone"
                stroke="var(--color-predicted)"
                strokeWidth={2}
                strokeDasharray="5 5"
                dot={false}
              />
            )}
          </LineChart>
        </ChartContainer>
      </CardContent>
      {metrics && (
        <CardFooter className="flex flex-wrap gap-2">
          {metrics.mae !== undefined && <Badge variant="outline">MAE: {metrics.mae.toFixed(1)}</Badge>}
          {metrics.smape !== undefined && <Badge variant="outline">sMAPE: {metrics.smape.toFixed(1)}%</Badge>}
          {metrics.wape !== undefined && <Badge variant="outline">WAPE: {metrics.wape.toFixed(1)}%</Badge>}
          {metrics.bias !== undefined && <Badge variant="outline">Bias: {metrics.bias.toFixed(1)}</Badge>}
        </CardFooter>
      )}
    </Card>
  )
}
```

**Required shadcn components:** `chart`, `card`, `badge`
**Add command:** `npx shadcn@latest add chart card badge`

---

### ChatMessage

Uses shadcn/ui primitives for layout with `collapsible` for tool calls.

```tsx
// components/chat/chat-message.tsx
"use client"

import { cn } from "@/lib/utils"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { ChevronDown } from "lucide-react"

interface Citation {
  id: string
  sourceType: string
  sourcePath: string
  snippet?: string
}

interface ToolCall {
  id: string
  name: string
  args: Record<string, unknown>
  result?: string
}

interface ChatMessageProps {
  role: "user" | "assistant"
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
    <div className={cn("flex", role === "user" ? "justify-end" : "justify-start")}>
      <Card className={cn("max-w-[80%]", role === "user" && "bg-primary text-primary-foreground")}>
        <CardContent className="p-4 space-y-3">
          {/* Message content */}
          <div className="prose prose-sm dark:prose-invert">
            {content}
            {isStreaming && <span className="animate-pulse ml-1">▋</span>}
          </div>

          {/* Citations */}
          {citations && citations.length > 0 && (
            <div className="border-t pt-2 space-y-1">
              <p className="text-xs font-medium text-muted-foreground">Citations:</p>
              <div className="flex flex-wrap gap-1">
                {citations.map((c) => (
                  <Badge key={c.id} variant="secondary" className="text-xs">
                    [{c.id}] {c.sourcePath}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Tool Calls */}
          {toolCalls && toolCalls.length > 0 && (
            <Collapsible>
              <CollapsibleTrigger asChild>
                <Button variant="ghost" size="sm" className="w-full justify-between">
                  <span>🔧 {toolCalls.length} tool call(s)</span>
                  <ChevronDown className="h-4 w-4" />
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent className="space-y-2 mt-2">
                {toolCalls.map((tc) => (
                  <div key={tc.id} className="text-xs bg-muted rounded p-2">
                    <p className="font-mono font-medium">{tc.name}</p>
                    <pre className="text-muted-foreground overflow-x-auto">
                      {JSON.stringify(tc.args, null, 2)}
                    </pre>
                  </div>
                ))}
              </CollapsibleContent>
            </Collapsible>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
```

**Required shadcn components:** `card`, `badge`, `button`, `collapsible`
**Add command:** `npx shadcn@latest add card badge button collapsible`

---

## API HOOKS (TanStack Query)

```tsx
// hooks/use-sales.ts
import { useQuery, keepPreviousData } from "@tanstack/react-query"
import { api } from "@/lib/api"

interface SalesQueryParams {
  page: number
  pageSize: number
  startDate?: string
  endDate?: string
  storeId?: number
  productId?: number
}

export function useSales(params: SalesQueryParams) {
  return useQuery({
    queryKey: ["sales", params],
    queryFn: () => api.get("/analytics/drilldowns", { params }),
    placeholderData: keepPreviousData,
  })
}

// hooks/use-runs.ts
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"

interface RunsQueryParams {
  page: number
  pageSize: number
  modelType?: string
  status?: string
  storeId?: number
  productId?: number
}

export function useRuns(params: RunsQueryParams) {
  return useQuery({
    queryKey: ["runs", params],
    queryFn: () => api.get("/registry/runs", { params }),
  })
}

// hooks/use-chat.ts
import { useState, useCallback, useEffect, useRef } from "react"

interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  citations?: Citation[]
  toolCalls?: ToolCall[]
}

export function useChat(sessionId?: string) {
  const [messages, setMessages] = useState<Message[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    const ws = new WebSocket(`${import.meta.env.VITE_WS_URL}`)
    wsRef.current = ws

    ws.onopen = () => setIsConnected(true)
    ws.onclose = () => setIsConnected(false)
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      // Handle streaming tokens, complete messages, etc.
      if (data.type === "token") {
        setMessages((prev) => {
          const last = prev[prev.length - 1]
          if (last?.role === "assistant") {
            return [...prev.slice(0, -1), { ...last, content: last.content + data.token }]
          }
          return [...prev, { id: crypto.randomUUID(), role: "assistant", content: data.token }]
        })
      }
    }

    return () => ws.close()
  }, [sessionId])

  const sendMessage = useCallback((content: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return

    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "user", content }])
    wsRef.current.send(JSON.stringify({
      type: "query",
      agent: "rag_assistant",
      payload: { query: content },
    }))
  }, [])

  return { messages, sendMessage, isConnected }
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

## OTHER CONSIDERATIONS

- **No Hardcoded URLs**: API base URL from environment variable only
- **Error Boundaries**: Graceful error handling with retry options
- **Loading States**: Skeleton components for all async data
- **Optimistic Updates**: Instant UI feedback for mutations
- **Caching**: TanStack Query manages cache invalidation
- **Bundle Size**: Code splitting per route for fast initial load

### shadcn/ui Installation Checklist

Run these commands to install all required components:

```bash
# Initialize shadcn/ui (if not already done)
npx shadcn@latest init

# Core layout components
npx shadcn@latest add card tabs navigation-menu sheet scroll-area separator

# Data display components
npx shadcn@latest add table badge skeleton pagination progress

# Form components
npx shadcn@latest add button input select textarea calendar popover checkbox

# Feedback components
npx shadcn@latest add sonner tooltip alert-dialog dialog

# Interactive components
npx shadcn@latest add collapsible accordion dropdown-menu

# Chart components (wraps Recharts)
npx shadcn@latest add chart
```

### Theme Configuration

shadcn/ui uses CSS variables for theming. Ensure your `globals.css` includes the theme variables:

```css
@layer base {
  :root {
    --chart-1: 221.2 83.2% 53.3%;
    --chart-2: 142.1 76.2% 36.3%;
    --chart-3: 47.9 95.8% 53.1%;
    --chart-4: 24.6 95% 53.1%;
    --chart-5: 280.1 93.6% 53.1%;
  }

  .dark {
    --chart-1: 217.2 91.2% 59.8%;
    --chart-2: 142.1 70.6% 45.3%;
    --chart-3: 47.9 95.8% 53.1%;
    --chart-4: 24.6 95% 53.1%;
    --chart-5: 280.1 93.6% 53.1%;
  }
}
```

### File Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── ui/              # shadcn/ui components (auto-generated)
│   │   ├── data-table/      # DataTable wrapper
│   │   ├── charts/          # Chart components
│   │   ├── chat/            # Chat components
│   │   └── layout/          # App shell, nav
│   ├── hooks/               # TanStack Query hooks
│   ├── lib/
│   │   ├── api.ts           # API client
│   │   └── utils.ts         # cn() utility
│   ├── pages/               # Route pages
│   └── App.tsx
├── .env.example
├── package.json
├── tailwind.config.js
└── vite.config.ts
```
