# INITIAL-11B.md — ForecastLab Dashboard (The Face)

> **Part B of 3**: Page Structure and UX Flows
> See also: [INITIAL-11A.md](./INITIAL-11A.md) (Overview, Tech Stack) | [INITIAL-11C.md](./INITIAL-11C.md) (Components, Hooks, Config)

---

## PAGE STRUCTURE

### Route Overview

| Route | Description | Primary shadcn Components |
|-------|-------------|---------------------------|
| `/dashboard` | KPI summary cards and quick actions | `card`, `badge`, `chart` |
| `/explorer/sales` | Sales data explorer | `table`, `input`, `select`, `popover`+`calendar` |
| `/explorer/runs` | Model run explorer | `table`, `checkbox`, `badge`, `button` |
| `/visualize/forecast` | Forecast visualization | `chart`, `card`, `select`, `badge` |
| `/visualize/backtest` | Backtest fold visualization | `chart`, `card`, `progress`, `badge` |
| `/chat` | Agent chat interface | `scroll-area`, `card`, `collapsible`, `textarea` |
| `/admin` | Admin panel | `tabs`, `table`, `alert-dialog`, `dialog` |

---

### /dashboard
Main dashboard with KPI summary cards and quick actions.

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
│  │  • RAG source indexed: CLAUDE.md (1d ago)               │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

**Recommended shadcn components:**
- `card` with `CardHeader`, `CardTitle`, `CardContent`, `CardFooter` - KPI cards
- `badge` - Trend indicators (+12.3%)
- `button` - Quick action links
- `separator` - Section dividers

---

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

**Layout Pattern:**
1. Page header with title + export button
2. Filter toolbar (collapsible on mobile)
3. Data table with server-side pagination
4. Pagination footer

**Recommended shadcn components:**
- `card` - Page container
- `button` - Export action
- `popover` + `calendar` - Date range picker
- `select` - Store/Product dropdowns
- `input` - Search input
- `table` - Data display (Table, TableHeader, TableBody, etc.)
- `pagination` - Page navigation
- `skeleton` - Loading rows
- `badge` - Optional status indicators

**Date Range Picker Pattern (validated):**
```tsx
<Popover>
  <PopoverTrigger asChild>
    <Button variant="outline">
      <CalendarIcon className="mr-2 h-4 w-4" />
      {dateRange?.from ? format(dateRange.from, "LLL dd") : "Pick date"}
    </Button>
  </PopoverTrigger>
  <PopoverContent className="w-auto p-0" align="start">
    <Calendar mode="range" selected={dateRange} onSelect={setDateRange} numberOfMonths={2} />
  </PopoverContent>
</Popover>
```

---

### /explorer/runs
Model run explorer with comparison capabilities.

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

**Recommended shadcn components:**
- `checkbox` - Row selection
- `badge` - Status column (variant based on status)
- `button` - Compare action (disabled until 2+ selected)
- `dropdown-menu` - Row actions (View, Archive, Delete)
- `table` - Data display
- `select` - Filter dropdowns

**Status Badge Variants:**
```tsx
const statusVariant = {
  SUCCESS: "default",     // Green
  FAILED: "destructive",  // Red
  RUNNING: "secondary",   // Gray/animated
  PENDING: "outline",     // Outline
}
<Badge variant={statusVariant[status]}>{status}</Badge>
```

---

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

**Recommended shadcn components:**
- `card` - Chart container (CardHeader for controls, CardContent for chart, CardFooter for metrics)
- `select` - Store, Product, Model Run selectors
- `popover` + `calendar` - Date range
- `chart` - ChartContainer wrapping Recharts LineChart
- `badge` - Metric display in footer

**Chart Pattern (using shadcn chart):**
```tsx
<Card>
  <CardHeader>
    <CardTitle>Forecast: {storeName}, {productName}</CardTitle>
    <div className="flex gap-2">
      <Select value={storeId} onValueChange={setStoreId}>...</Select>
      <Select value={productId} onValueChange={setProductId}>...</Select>
    </div>
  </CardHeader>
  <CardContent>
    <ChartContainer config={chartConfig}>
      <LineChart data={data}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="date" />
        <ChartTooltip content={<ChartTooltipContent />} />
        <Line dataKey="actual" stroke="var(--color-actual)" />
        <Line dataKey="predicted" stroke="var(--color-predicted)" strokeDasharray="5 5" />
      </LineChart>
    </ChartContainer>
  </CardContent>
  <CardFooter className="flex gap-4">
    <Badge variant="outline">MAE: {mae}</Badge>
    <Badge variant="outline">sMAPE: {smape}%</Badge>
  </CardFooter>
</Card>
```

---

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

**Recommended shadcn components:**
- `card` - Container
- `progress` - Train/test bar visualization (stacked or dual-color)
- `badge` - Metrics display
- `separator` - Between folds and aggregated metrics
- `collapsible` - Fold details (expand to show predictions)

**Fold Visualization Pattern:**
```tsx
{folds.map((fold, i) => (
  <div key={i} className="flex items-center gap-4">
    <span className="w-16">Fold {i + 1}:</span>
    <div className="flex-1 flex h-4 rounded overflow-hidden">
      <div className="bg-primary" style={{ width: `${fold.trainPct}%` }} />
      <div className="bg-muted" style={{ width: `${fold.testPct}%` }} />
    </div>
    <Badge variant="outline">MAE: {fold.mae}</Badge>
    <Badge variant="outline">sMAPE: {fold.smape}%</Badge>
  </div>
))}
```

---

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

**Layout Pattern (Desktop):**
- Left: Session list (narrow column, ~200px)
- Right: Chat area with messages + input

**Layout Pattern (Mobile):**
- Sheet drawer for session list
- Full-width chat area

**Recommended shadcn components:**
- `card` - Message containers
- `scroll-area` - Message list scrolling
- `collapsible` - Tool call details (collapsed by default)
- `accordion` - Multiple tool calls grouped
- `textarea` - Message input
- `button` - Send button
- `badge` - Citation source type
- `skeleton` - Streaming placeholder
- `sheet` - Mobile session drawer
- `separator` - Between citations and tool calls

**Message Structure:**
```tsx
<div className={cn("flex", role === "user" ? "justify-end" : "justify-start")}>
  <Card className="max-w-[80%]">
    <CardContent className="p-4">
      <Markdown>{content}</Markdown>
      {isStreaming && <span className="animate-pulse">▋</span>}

      {citations && (
        <div className="mt-4 border-t pt-2">
          <p className="text-sm font-medium">Citations:</p>
          {citations.map(c => (
            <Badge key={c.id} variant="outline">{c.source}</Badge>
          ))}
        </div>
      )}

      {toolCalls && (
        <Collapsible>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" size="sm">
              🔧 {toolCalls.length} tool call(s)
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            {toolCalls.map(tc => <ToolCallCard key={tc.id} {...tc} />)}
          </CollapsibleContent>
        </Collapsible>
      )}
    </CardContent>
  </Card>
</div>
```

---

### /admin
Admin panel for system management.

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
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Layout Pattern:**
- Use `tabs` for section switching (RAG Sources, Model Aliases, Jobs, Health)
- Each tab contains a table or card-based layout

**Recommended shadcn components:**
- `tabs` - Section navigation (TabsList, TabsTrigger, TabsContent)
- `table` - Data lists
- `button` - Actions (Index New, Create Alias)
- `dropdown-menu` - Row actions (Re-index, Delete)
- `alert-dialog` - Delete confirmation
- `dialog` - Create/edit forms
- `badge` - Status indicators
- `sonner` - Action feedback

**Delete Confirmation Pattern:**
```tsx
<AlertDialog>
  <AlertDialogTrigger asChild>
    <DropdownMenuItem className="text-destructive">Delete</DropdownMenuItem>
  </AlertDialogTrigger>
  <AlertDialogContent>
    <AlertDialogHeader>
      <AlertDialogTitle>Delete Source?</AlertDialogTitle>
      <AlertDialogDescription>
        This will remove "{sourceName}" and all its indexed chunks.
        This action cannot be undone.
      </AlertDialogDescription>
    </AlertDialogHeader>
    <AlertDialogFooter>
      <AlertDialogCancel>Cancel</AlertDialogCancel>
      <AlertDialogAction onClick={handleDelete} className="bg-destructive">
        Delete
      </AlertDialogAction>
    </AlertDialogFooter>
  </AlertDialogContent>
</AlertDialog>
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
