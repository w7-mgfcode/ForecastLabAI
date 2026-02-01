# INITIAL-11C.md — ForecastLab Dashboard (The Face)

> **Part C of 3**: Pages & Components
> See also: [INITIAL-11A.md](./INITIAL-11A.md) (Setup & Config) | [INITIAL-11B.md](./INITIAL-11B.md) (Architecture & Features)

---

## Route Overview

| Route | Description | API Endpoint |
|-------|-------------|--------------|
| `/dashboard` | KPI summary cards | GET /analytics/kpis |
| `/explorer/sales` | Sales data table | GET /analytics/drilldowns |
| `/explorer/runs` | Model run table | GET /registry/runs |
| `/visualize/forecast` | Forecast chart | GET /forecasting/predict |
| `/visualize/backtest` | Backtest folds | GET /backtesting/results/{run_id} |
| `/chat` | Agent chat | WS /agents/stream |
| `/admin` | Admin panel | GET /rag/sources, /registry/aliases |

---

## Page Wireframes

### /dashboard

```
┌─────────────────────────────────────────────────────────────┐
│  [Logo] ForecastLab    [Dashboard] [Explorer▼] [Visualize▼] │
│                        [Chat] [Admin]          [Theme] [?]  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ Total Sales │  │ Active Runs │  │ RAG Sources │         │
│  │   $2.4M     │  │     127     │  │      15     │         │
│  │   +12.3%    │  │   +5 today  │  │   indexed   │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  Recent Activity                                [See All]│
│  │  • Backtest run_abc completed (2h ago)                  │
│  │  • Model alias "production" updated (5h ago)            │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### /explorer/sales

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

```
┌─────────────────────────────────────────────────────────────┐
│  Model Runs                              [Compare Selected] │
├─────────────────────────────────────────────────────────────┤
│  Filters: [Model Type ▼] [Status ▼] [Store ▼] [Product ▼]  │
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

```
┌─────────────────────────────────────────────────────────────┐
│  Admin Panel                                                │
├─────────────────────────────────────────────────────────────┤
│  [RAG Sources] [Model Aliases] [Jobs] [Health]              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  RAG Sources                                   [+ Index New] │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ Source          │ Type     │ Chunks │ Indexed    │ ⋮   ││
│  │ CLAUDE.md       │ markdown │ 45     │ 2h ago     │ [⋮] ││
│  │ README.md       │ markdown │ 23     │ 1d ago     │ [⋮] ││
│  │ openapi.yaml    │ openapi  │ 78     │ 3d ago     │ [⋮] ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

---

## Component Patterns

### DataTable

Uses [shadcn/ui Data Table](https://ui.shadcn.com/docs/components/data-table) with TanStack Table.

```tsx
// components/data-table/data-table.tsx
"use client"

import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
  type PaginationState,
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
  isLoading?: boolean
}

export function DataTable<TData, TValue>({
  columns, data, pageCount, pagination, onPaginationChange, isLoading,
}: DataTableProps<TData, TValue>) {
  const table = useReactTable({
    data,
    columns,
    pageCount,
    state: { pagination },
    onPaginationChange: (updater) => {
      const next = typeof updater === "function" ? updater(pagination) : updater
      onPaginationChange(next)
    },
    manualPagination: true,
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
                    {flexRender(header.column.columnDef.header, header.getContext())}
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
            ) : table.getRowModel().rows.map((row) => (
              <TableRow key={row.id}>
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <div className="flex justify-end space-x-2">
        <Button variant="outline" size="sm" onClick={() => table.previousPage()} disabled={!table.getCanPreviousPage()}>
          Previous
        </Button>
        <Button variant="outline" size="sm" onClick={() => table.nextPage()} disabled={!table.getCanNextPage()}>
          Next
        </Button>
      </div>
    </div>
  )
}
```

### TimeSeriesChart

Uses shadcn/ui `chart` wrapping Recharts.

```tsx
// components/charts/time-series-chart.tsx
"use client"

import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts"
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Badge } from "@/components/ui/badge"

const chartConfig = {
  actual: { label: "Actual", color: "var(--chart-1)" },
  predicted: { label: "Predicted", color: "var(--chart-2)" },
} satisfies ChartConfig

interface Props {
  title: string
  data: { date: string; actual: number; predicted?: number }[]
  metrics?: { mae?: number; smape?: number }
}

export function TimeSeriesChart({ title, data, metrics }: Props) {
  return (
    <Card>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardContent>
        <ChartContainer config={chartConfig} className="h-[350px] w-full">
          <LineChart data={data}>
            <CartesianGrid vertical={false} />
            <XAxis dataKey="date" tickLine={false} axisLine={false} />
            <YAxis tickLine={false} axisLine={false} />
            <ChartTooltip content={<ChartTooltipContent />} />
            <Line dataKey="actual" stroke="var(--color-actual)" strokeWidth={2} dot={false} />
            <Line dataKey="predicted" stroke="var(--color-predicted)" strokeWidth={2} strokeDasharray="5 5" dot={false} />
          </LineChart>
        </ChartContainer>
      </CardContent>
      {metrics && (
        <CardFooter className="flex gap-2">
          {metrics.mae && <Badge variant="outline">MAE: {metrics.mae.toFixed(1)}</Badge>}
          {metrics.smape && <Badge variant="outline">sMAPE: {metrics.smape.toFixed(1)}%</Badge>}
        </CardFooter>
      )}
    </Card>
  )
}
```

### ChatMessage

Uses `collapsible` for tool calls.

```tsx
// components/chat/chat-message.tsx
"use client"

import { cn } from "@/lib/utils"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"

interface Props {
  role: "user" | "assistant"
  content: string
  citations?: { id: string; sourcePath: string }[]
  toolCalls?: { id: string; name: string }[]
  isStreaming?: boolean
}

export function ChatMessage({ role, content, citations, toolCalls, isStreaming }: Props) {
  return (
    <div className={cn("flex", role === "user" ? "justify-end" : "justify-start")}>
      <Card className={cn("max-w-[80%]", role === "user" && "bg-primary text-primary-foreground")}>
        <CardContent className="p-4 space-y-3">
          <div className="prose prose-sm dark:prose-invert">
            {content}
            {isStreaming && <span className="animate-pulse ml-1">▋</span>}
          </div>

          {citations?.length > 0 && (
            <div className="border-t pt-2">
              <p className="text-xs font-medium text-muted-foreground">Citations:</p>
              <div className="flex flex-wrap gap-1">
                {citations.map((c) => (
                  <Badge key={c.id} variant="secondary" className="text-xs">[{c.id}] {c.sourcePath}</Badge>
                ))}
              </div>
            </div>
          )}

          {toolCalls?.length > 0 && (
            <Collapsible>
              <CollapsibleTrigger asChild>
                <Button variant="ghost" size="sm">🔧 {toolCalls.length} tool call(s)</Button>
              </CollapsibleTrigger>
              <CollapsibleContent className="space-y-2 mt-2">
                {toolCalls.map((tc) => (
                  <div key={tc.id} className="text-xs bg-muted rounded p-2 font-mono">{tc.name}</div>
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

### DateRangePicker

Uses `popover` + `calendar`.

```tsx
// components/date-range-picker.tsx
"use client"

import { format } from "date-fns"
import { CalendarIcon } from "lucide-react"
import { type DateRange } from "react-day-picker"
import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"

interface Props {
  value?: DateRange
  onChange: (range: DateRange | undefined) => void
}

export function DateRangePicker({ value, onChange }: Props) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" className="w-[280px] justify-start text-left">
          <CalendarIcon className="mr-2 h-4 w-4" />
          {value?.from ? (
            value.to ? `${format(value.from, "LLL dd")} - ${format(value.to, "LLL dd")}` : format(value.from, "LLL dd")
          ) : "Pick a date range"}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar mode="range" selected={value} onSelect={onChange} numberOfMonths={2} />
      </PopoverContent>
    </Popover>
  )
}
```

### StatusBadge

```tsx
// components/status-badge.tsx
import { Badge } from "@/components/ui/badge"

const variants = {
  SUCCESS: "default",
  FAILED: "destructive",
  RUNNING: "secondary",
  PENDING: "outline",
} as const

export function StatusBadge({ status }: { status: keyof typeof variants }) {
  return <Badge variant={variants[status]}>{status}</Badge>
}
```

---

## API Hooks

```tsx
// hooks/use-sales.ts
import { useQuery, keepPreviousData } from "@tanstack/react-query"
import { api } from "@/lib/api"

export function useSales(params: { page: number; pageSize: number; storeId?: number }) {
  return useQuery({
    queryKey: ["sales", params],
    queryFn: () => api.get("/analytics/drilldowns", { params }),
    placeholderData: keepPreviousData,
  })
}

// hooks/use-runs.ts
export function useRuns(params: { page: number; pageSize: number; status?: string }) {
  return useQuery({
    queryKey: ["runs", params],
    queryFn: () => api.get("/registry/runs", { params }),
  })
}

// hooks/use-chat.ts
import { useState, useCallback, useEffect, useRef } from "react"

export function useChat() {
  const [messages, setMessages] = useState<{ id: string; role: "user" | "assistant"; content: string }[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    const ws = new WebSocket(import.meta.env.VITE_WS_URL)
    wsRef.current = ws
    ws.onopen = () => setIsConnected(true)
    ws.onclose = () => setIsConnected(false)
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
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
  }, [])

  const sendMessage = useCallback((content: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "user", content }])
    wsRef.current.send(JSON.stringify({ type: "query", agent: "rag_assistant", payload: { query: content } }))
  }, [])

  return { messages, sendMessage, isConnected }
}
```

---

## Delete Confirmation Pattern

```tsx
// Used in Admin panel for destructive actions
<AlertDialog>
  <AlertDialogTrigger asChild>
    <DropdownMenuItem className="text-destructive">Delete</DropdownMenuItem>
  </AlertDialogTrigger>
  <AlertDialogContent>
    <AlertDialogHeader>
      <AlertDialogTitle>Delete Source?</AlertDialogTitle>
      <AlertDialogDescription>
        This will remove "{sourceName}" and all its indexed chunks. This action cannot be undone.
      </AlertDialogDescription>
    </AlertDialogHeader>
    <AlertDialogFooter>
      <AlertDialogCancel>Cancel</AlertDialogCancel>
      <AlertDialogAction onClick={handleDelete} className="bg-destructive">Delete</AlertDialogAction>
    </AlertDialogFooter>
  </AlertDialogContent>
</AlertDialog>
```

---

## Documentation Links

- [shadcn/ui Data Table](https://ui.shadcn.com/docs/components/data-table)
- [shadcn/ui Charts](https://ui.shadcn.com/docs/components/chart)
- [TanStack Table Server-Side](https://tanstack.com/table/latest/docs/guide/pagination#manual-server-side-pagination)
- [TanStack Query](https://tanstack.com/query/latest)
- [Recharts](https://recharts.org/)
- [React Day Picker](https://react-day-picker.js.org/)

---

## Other Considerations

- **Server-Side Operations**: All pagination, sorting, filtering is manual (server-side)
- **Loading States**: Use `Skeleton` for all async data
- **Error Handling**: Wrap pages in error boundaries
- **Accessibility**: All components support keyboard navigation
- **Mobile**: Use `sheet` for navigation, responsive tables
- **Bundle Size**: Code split by route for fast initial load

---

## Running the Dashboard

```bash
cd frontend
pnpm install
pnpm dev
```

Open http://localhost:5173
