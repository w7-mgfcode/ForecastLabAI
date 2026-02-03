# INITIAL-13.md — Data Seeder Dashboard (The Forge UI)

## Architectural Role

**"The Forge UI"** - Admin interface for managing synthetic data generation using The Forge seeder.

This phase provides the visual layer for:
- Viewing current database state (row counts, date ranges)
- Triggering data generation operations (full-new, append, delete)
- Selecting pre-built scenarios and configuring parameters
- Monitoring operation progress and viewing logs
- Verifying data integrity

---

## RESEARCH PHASE

### Codebase Analysis

**Existing Frontend Patterns Reviewed:**
- `frontend/src/pages/admin.tsx` — Tabbed admin panel with Cards, Dialogs, AlertDialogs
- `frontend/src/pages/dashboard.tsx` — KPI cards layout, data hooks pattern
- `frontend/src/components/ui/` — 26 shadcn/ui components already installed
- `frontend/src/hooks/` — TanStack Query patterns for data fetching
- `frontend/src/lib/api.ts` — API client with RFC 7807 error handling

**Available shadcn/ui Components (Already Installed):**
| Component | Use Case in Forge UI |
|-----------|---------------------|
| `Card` | KPI summary cards, configuration panels |
| `Tabs` | Switch between Operations/Config/Logs views |
| `Button` | Action triggers (Generate, Delete, Append) |
| `AlertDialog` | Confirmation for destructive operations |
| `Dialog` | Configuration modals |
| `Select` | Scenario picker, scope selector |
| `Input` | Seed, stores, products inputs |
| `Calendar` | Date range picker |
| `Progress` | Operation progress indicator |
| `Badge` | Status indicators |
| `Table` | Row count summary, verification results |
| `Accordion` | Collapsible log sections |
| `Skeleton` | Loading states |
| `Sonner` | Toast notifications |

**Backend API (scripts/seed_random.py):**
- CLI-based (no REST endpoints yet)
- Operations: `--full-new`, `--delete`, `--append`, `--status`, `--verify`
- Configuration: `--seed`, `--stores`, `--products`, `--start-date`, `--end-date`, `--scenario`

---

## BRAINSTORM PHASE

### Core Features (Required)

1. **Data Status Dashboard** — Current row counts for all 7 tables
2. **Quick Actions** — One-click operations with confirmation
3. **Scenario Selector** — Pre-built scenario presets
4. **Configuration Form** — Custom parameters (seed, counts, dates)
5. **Operation Log** — Real-time output from seeder operations

### Additional Features (Brainstormed)

#### Visual Data Summary
- **Date Range Indicator** — Min/max dates in sales_daily
- **Coverage Heatmap** — Store × Product matrix showing data density
- **Trend Preview** — Small sparkline of daily sales totals

#### Advanced Configuration
- **YAML Editor** — Edit custom configuration inline
- **Preset Manager** — Save/load custom configurations
- **Dry Run Toggle** — Preview changes before executing

#### Operation Management
- **Progress Streaming** — WebSocket-based real-time progress
- **Cancel Operation** — Abort long-running operations
- **History Log** — Past operations with timestamps and parameters

#### Data Quality
- **Verification Panel** — FK integrity, constraint checks, gap detection
- **Data Preview** — Sample rows from generated data
- **Export Config** — Download YAML for reproducibility

---

## DECISION PHASE

### Architecture Decision: Backend Integration

| Option | Pros | Cons |
|--------|------|------|
| **REST API Endpoints** (Recommended) | Standard patterns, async-ready | Requires new routes |
| Direct CLI Execution | Immediate, no backend changes | Not web-friendly |
| WebSocket Streaming | Real-time progress | Complex implementation |

**Decision**: Create new REST API endpoints in `app/features/seeder/` feature slice:
- `GET /seeder/status` — Current table row counts
- `POST /seeder/generate` — Trigger full-new generation
- `POST /seeder/append` — Append data to existing dataset
- `DELETE /seeder/data` — Delete data with scope
- `POST /seeder/verify` — Run integrity verification
- `GET /seeder/scenarios` — List available scenarios

### UI Layout Decision

| Option | Pros | Cons |
|--------|------|------|
| **New Tab in Admin** (Recommended) | Consistent with existing admin | Adds to existing complexity |
| Standalone Page | Clean separation | Navigation overhead |
| Dashboard Widget | Quick access | Limited space |

**Decision**: Add new "Data Seeder" tab to existing `/admin` page, following the Tabs pattern from RAG Sources and Aliases panels.

---

## FEATURE

### Data Status Panel

Real-time view of current database state:

```
┌─────────────────────────────────────────────────────────────┐
│  Current Data Summary                            [Refresh]  │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────┬─────────┬─────────┬─────────┬─────────┐       │
│  │ Stores  │Products │Calendar │ Sales   │Inventory│       │
│  │   10    │   50    │  365    │ 127,450 │ 182,500 │       │
│  │   +0%   │   +0%   │   +0%   │  +12%   │   +8%   │       │
│  └─────────┴─────────┴─────────┴─────────┴─────────┘       │
│                                                             │
│  Date Range: 2024-01-01 → 2024-12-31 (365 days)            │
│  Last Updated: 2 hours ago                                  │
└─────────────────────────────────────────────────────────────┘
```

**Components Used:**
- `Card` with `CardHeader`, `CardContent`
- Grid of stat cards with `Badge` for change indicators
- `Skeleton` for loading states

### Quick Actions Panel

One-click operations with confirmation dialogs:

```
┌─────────────────────────────────────────────────────────────┐
│  Quick Actions                                              │
├─────────────────────────────────────────────────────────────┤
│  [🔄 Generate New Dataset]  [➕ Append Data]  [🗑️ Delete]   │
│                                                             │
│  ○ retail_standard (default)                                │
│  ○ holiday_rush                                             │
│  ○ high_variance                                            │
│  ○ stockout_heavy                                           │
│  ○ new_launches                                             │
│  ○ sparse                                                   │
└─────────────────────────────────────────────────────────────┘
```

**Components Used:**
- `Button` with variants (default, destructive)
- `AlertDialog` for delete confirmation
- Radio group for scenario selection (using multiple `Button` with `variant="outline"`)

### Configuration Panel

Detailed parameter configuration:

```
┌─────────────────────────────────────────────────────────────┐
│  Configuration                                              │
├─────────────────────────────────────────────────────────────┤
│  Seed          [42        ]   Stores      [10       ]       │
│  Products      [50        ]   Batch Size  [1000     ]       │
│                                                             │
│  Date Range                                                 │
│  Start: [📅 2024-01-01]      End: [📅 2024-12-31]          │
│                                                             │
│  Advanced Options                                           │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Sparsity: [0.0    ]  (0.0 - 1.0)                    │  │
│  │  ☐ Dry Run (preview only)                            │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  [Apply Configuration]                                      │
└─────────────────────────────────────────────────────────────┘
```

**Components Used:**
- `Input` for numeric values
- `Calendar` + `Popover` for date pickers
- `Checkbox` for dry run toggle
- `Accordion` for advanced options
- `Button` for apply action

### Operation Log Panel

Real-time operation output:

```
┌─────────────────────────────────────────────────────────────┐
│  Operation Log                                    [Clear]   │
├─────────────────────────────────────────────────────────────┤
│  ▶ Running: Generate New Dataset (seed: 42)                 │
│  ████████████████████░░░░░░░░░░  65% - Generating sales...  │
│  ────────────────────────────────────────────────────────   │
│  2026-02-02 10:30:15  ✓ Generated 10 stores                 │
│  2026-02-02 10:30:16  ✓ Generated 50 products               │
│  2026-02-02 10:30:17  ✓ Generated 365 calendar days         │
│  2026-02-02 10:30:45  ⏳ Generating sales records...        │
│  2026-02-02 10:30:45    Batch 1/128 complete                │
│  2026-02-02 10:30:46    Batch 2/128 complete                │
│  ...                                                         │
└─────────────────────────────────────────────────────────────┘
```

**Components Used:**
- `Card` with fixed height and `ScrollArea`
- `Progress` bar for operation progress
- `Badge` for status indicators (success, error, pending)
- Monospace font for log entries

### Verification Panel

Data integrity check results:

```
┌─────────────────────────────────────────────────────────────┐
│  Data Verification                              [Run Check] │
├─────────────────────────────────────────────────────────────┤
│  Last Run: 2026-02-02 10:35:00                              │
│                                                             │
│  ✓ Foreign Key Integrity          PASSED                   │
│  ✓ Non-Negative Constraints       PASSED                   │
│  ✓ Date Range Coverage            PASSED                   │
│  ✓ Unique Constraints             PASSED                   │
│  ⚠ Data Gaps Detected             2 gaps found             │
│                                                             │
│  Gaps:                                                      │
│  - Store S003, Product P012: 2024-03-15 to 2024-03-17      │
│  - Store S007, Product P045: 2024-08-01 to 2024-08-03      │
└─────────────────────────────────────────────────────────────┘
```

**Components Used:**
- `Table` for check results
- `Badge` with variants (success, warning, destructive)
- `Accordion` for expandable details

---

## PAGE STRUCTURE

### /admin (Extended with Seeder Tab)

```
┌─────────────────────────────────────────────────────────────┐
│  Admin Panel                                                │
├─────────────────────────────────────────────────────────────┤
│  [📚 RAG Sources] [🏷️ Deployment Aliases] [🔥 Data Seeder] │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─ Data Status ──────────────────────────────────────────┐ │
│  │  [Store: 10] [Products: 50] [Days: 365] [Sales: 127K]  │ │
│  │  Date Range: 2024-01-01 → 2024-12-31                   │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌─ Quick Actions ────────────────────────────────────────┐ │
│  │  [🔄 Generate] [➕ Append] [🗑️ Delete] [✓ Verify]      │ │
│  │                                                         │ │
│  │  Scenario: [retail_standard ▼]                         │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌─ Configuration ────────────────────────────────────────┐ │
│  │  Seed: [42] Stores: [10] Products: [50]                │ │
│  │  Dates: [2024-01-01] to [2024-12-31]                   │ │
│  │  [▸ Advanced Options]                                  │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌─ Operation Log ────────────────────────────────────────┐ │
│  │  ████████████░░░░░░░░  60% Generating sales...         │ │
│  │  10:30:15 ✓ Generated 10 stores                        │ │
│  │  10:30:16 ✓ Generated 50 products                      │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## COMPONENTS

### SeederPanel (Main Component)

```tsx
// components/seeder/seeder-panel.tsx
import { useState } from 'react'
import { Flame, Plus, Trash2, CheckCircle, RefreshCw } from 'lucide-react'
import { useSeederStatus, useGenerateData, useDeleteData, useVerifyData } from '@/hooks/use-seeder'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dialog'

const SCENARIOS = [
  { value: 'retail_standard', label: 'Retail Standard', description: 'Normal retail patterns' },
  { value: 'holiday_rush', label: 'Holiday Rush', description: 'Q4 surge with peaks' },
  { value: 'high_variance', label: 'High Variance', description: 'Noisy, unpredictable' },
  { value: 'stockout_heavy', label: 'Stockout Heavy', description: 'Frequent stockouts' },
  { value: 'new_launches', label: 'New Launches', description: 'Product launch ramps' },
  { value: 'sparse', label: 'Sparse', description: 'Missing data patterns' },
]

export function SeederPanel() {
  const [scenario, setScenario] = useState('retail_standard')
  const { data: status, isLoading, refetch } = useSeederStatus()
  const generateMutation = useGenerateData()
  const deleteMutation = useDeleteData()

  return (
    <div className="space-y-6">
      <DataStatusCard status={status} isLoading={isLoading} onRefresh={refetch} />
      <QuickActionsCard
        scenario={scenario}
        onScenarioChange={setScenario}
        onGenerate={() => generateMutation.mutate({ scenario })}
        onDelete={() => deleteMutation.mutate({ scope: 'all' })}
        isGenerating={generateMutation.isPending}
        isDeleting={deleteMutation.isPending}
      />
      <ConfigurationCard />
      <OperationLogCard />
    </div>
  )
}
```

### DataStatusCard

```tsx
// components/seeder/data-status-card.tsx
interface DataStatusCardProps {
  status: SeederStatus | undefined
  isLoading: boolean
  onRefresh: () => void
}

export function DataStatusCard({ status, isLoading, onRefresh }: DataStatusCardProps) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Current Data Summary</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-5 gap-4">
            {[...Array(5)].map((_, i) => (
              <Skeleton key={i} className="h-20" />
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  const stats = [
    { label: 'Stores', value: status?.stores ?? 0, icon: Store },
    { label: 'Products', value: status?.products ?? 0, icon: Package },
    { label: 'Calendar', value: status?.calendar ?? 0, icon: Calendar },
    { label: 'Sales', value: status?.sales ?? 0, icon: TrendingUp },
    { label: 'Inventory', value: status?.inventory ?? 0, icon: Warehouse },
  ]

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>Current Data Summary</CardTitle>
          <CardDescription>
            {status?.date_range_start} → {status?.date_range_end}
          </CardDescription>
        </div>
        <Button variant="outline" size="sm" onClick={onRefresh}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Refresh
        </Button>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-5 gap-4">
          {stats.map((stat) => (
            <div key={stat.label} className="text-center p-4 rounded-lg bg-muted">
              <stat.icon className="h-5 w-5 mx-auto mb-2 text-muted-foreground" />
              <p className="text-2xl font-bold">{stat.value.toLocaleString()}</p>
              <p className="text-sm text-muted-foreground">{stat.label}</p>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
```

### QuickActionsCard

```tsx
// components/seeder/quick-actions-card.tsx
interface QuickActionsCardProps {
  scenario: string
  onScenarioChange: (scenario: string) => void
  onGenerate: () => void
  onDelete: () => void
  isGenerating: boolean
  isDeleting: boolean
}

export function QuickActionsCard({
  scenario,
  onScenarioChange,
  onGenerate,
  onDelete,
  isGenerating,
  isDeleting,
}: QuickActionsCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Quick Actions</CardTitle>
        <CardDescription>
          Generate, append, or delete synthetic data
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-2">
          <Button onClick={onGenerate} disabled={isGenerating}>
            {isGenerating ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Flame className="h-4 w-4 mr-2" />
            )}
            Generate New
          </Button>

          <Button variant="outline">
            <Plus className="h-4 w-4 mr-2" />
            Append Data
          </Button>

          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive" disabled={isDeleting}>
                <Trash2 className="h-4 w-4 mr-2" />
                Delete All
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Delete All Data?</AlertDialogTitle>
                <AlertDialogDescription>
                  This will permanently delete all generated data from the database.
                  This action cannot be undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={onDelete}>
                  Delete All Data
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>

          <Button variant="outline">
            <CheckCircle className="h-4 w-4 mr-2" />
            Verify
          </Button>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium">Scenario</label>
          <Select value={scenario} onValueChange={onScenarioChange}>
            <SelectTrigger className="w-[280px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SCENARIOS.map((s) => (
                <SelectItem key={s.value} value={s.value}>
                  <div className="flex flex-col">
                    <span>{s.label}</span>
                    <span className="text-xs text-muted-foreground">{s.description}</span>
                  </div>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </CardContent>
    </Card>
  )
}
```

---

## API HOOKS

```tsx
// hooks/use-seeder.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'

interface SeederStatus {
  stores: number
  products: number
  calendar: number
  sales: number
  inventory: number
  price_history: number
  promotions: number
  date_range_start: string | null
  date_range_end: string | null
  last_updated: string | null
}

interface GenerateParams {
  scenario?: string
  seed?: number
  stores?: number
  products?: number
  start_date?: string
  end_date?: string
  dry_run?: boolean
}

interface DeleteParams {
  scope: 'all' | 'facts' | 'dimensions'
}

interface VerifyResult {
  passed: boolean
  checks: Array<{
    name: string
    status: 'passed' | 'warning' | 'failed'
    message: string
    details?: string[]
  }>
}

export function useSeederStatus() {
  return useQuery({
    queryKey: ['seeder', 'status'],
    queryFn: () => api.get<SeederStatus>('/seeder/status'),
    refetchInterval: 30000, // Refresh every 30 seconds
  })
}

export function useGenerateData() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (params: GenerateParams) =>
      api.post('/seeder/generate', params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['seeder', 'status'] })
      queryClient.invalidateQueries({ queryKey: ['analytics'] })
    },
  })
}

export function useAppendData() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (params: GenerateParams) =>
      api.post('/seeder/append', params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['seeder', 'status'] })
    },
  })
}

export function useDeleteData() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (params: DeleteParams) =>
      api.delete('/seeder/data', { data: params }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['seeder', 'status'] })
      queryClient.invalidateQueries({ queryKey: ['analytics'] })
    },
  })
}

export function useVerifyData() {
  return useMutation({
    mutationFn: () => api.post<VerifyResult>('/seeder/verify'),
  })
}

export function useSeederScenarios() {
  return useQuery({
    queryKey: ['seeder', 'scenarios'],
    queryFn: () => api.get<Array<{ name: string; description: string }>>('/seeder/scenarios'),
    staleTime: Infinity, // Scenarios don't change
  })
}
```

---

## BACKEND API ENDPOINTS (New Feature Slice)

### Routes

```python
# app/features/seeder/routes.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.features.seeder import schemas, service

router = APIRouter(prefix="/seeder", tags=["seeder"])


@router.get("/status", response_model=schemas.SeederStatus)
async def get_status(db: AsyncSession = Depends(get_db)) -> schemas.SeederStatus:
    """Get current database row counts and date range."""
    return await service.get_status(db)


@router.get("/scenarios", response_model=list[schemas.ScenarioInfo])
async def list_scenarios() -> list[schemas.ScenarioInfo]:
    """List available scenario presets."""
    return service.list_scenarios()


@router.post("/generate", response_model=schemas.GenerateResult)
async def generate_data(
    params: schemas.GenerateParams,
    db: AsyncSession = Depends(get_db),
) -> schemas.GenerateResult:
    """Generate new synthetic dataset."""
    return await service.generate_data(db, params)


@router.post("/append", response_model=schemas.GenerateResult)
async def append_data(
    params: schemas.AppendParams,
    db: AsyncSession = Depends(get_db),
) -> schemas.GenerateResult:
    """Append data to existing dataset."""
    return await service.append_data(db, params)


@router.delete("/data", response_model=schemas.DeleteResult)
async def delete_data(
    params: schemas.DeleteParams,
    db: AsyncSession = Depends(get_db),
) -> schemas.DeleteResult:
    """Delete data with specified scope."""
    return await service.delete_data(db, params)


@router.post("/verify", response_model=schemas.VerifyResult)
async def verify_data(
    db: AsyncSession = Depends(get_db),
) -> schemas.VerifyResult:
    """Run data integrity verification."""
    return await service.verify_data(db)
```

### Schemas

```python
# app/features/seeder/schemas.py
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class SeederStatus(BaseModel):
    """Current database state."""
    stores: int
    products: int
    calendar: int
    sales: int
    inventory: int
    price_history: int
    promotions: int
    date_range_start: date | None
    date_range_end: date | None
    last_updated: str | None


class ScenarioInfo(BaseModel):
    """Scenario preset information."""
    name: str
    description: str
    stores: int
    products: int


class GenerateParams(BaseModel):
    """Parameters for data generation."""
    scenario: str = "retail_standard"
    seed: int = Field(default=42, ge=0)
    stores: int = Field(default=10, ge=1, le=100)
    products: int = Field(default=50, ge=1, le=500)
    start_date: date = Field(default_factory=lambda: date(2024, 1, 1))
    end_date: date = Field(default_factory=lambda: date(2024, 12, 31))
    sparsity: float = Field(default=0.0, ge=0.0, le=1.0)
    dry_run: bool = False


class AppendParams(BaseModel):
    """Parameters for appending data."""
    start_date: date
    end_date: date
    seed: int = Field(default=43, ge=0)


class DeleteParams(BaseModel):
    """Parameters for data deletion."""
    scope: Literal["all", "facts", "dimensions"] = "all"


class GenerateResult(BaseModel):
    """Result of generation operation."""
    success: bool
    records_created: dict[str, int]
    duration_seconds: float
    message: str


class DeleteResult(BaseModel):
    """Result of deletion operation."""
    success: bool
    records_deleted: dict[str, int]
    message: str


class VerifyCheck(BaseModel):
    """Single verification check result."""
    name: str
    status: Literal["passed", "warning", "failed"]
    message: str
    details: list[str] | None = None


class VerifyResult(BaseModel):
    """Data verification result."""
    passed: bool
    checks: list[VerifyCheck]
```

---

## CONFIGURATION

### Environment Variables

```env
# Seeder Configuration (already in CLAUDE.md)
SEEDER_DEFAULT_SEED=42
SEEDER_DEFAULT_STORES=10
SEEDER_DEFAULT_PRODUCTS=50
SEEDER_BATCH_SIZE=1000
SEEDER_ENABLE_PROGRESS=True
SEEDER_ALLOW_PRODUCTION=False
SEEDER_REQUIRE_CONFIRM=True
```

### Frontend Environment

```env
# frontend/.env
VITE_API_BASE_URL=http://localhost:8123
VITE_ENABLE_SEEDER_PANEL=true  # Feature flag for seeder UI
```

---

## EXAMPLES

### examples/ui/seeder-panel.md

```markdown
# Data Seeder Panel

## Quick Start

1. Navigate to Admin Panel: http://localhost:5173/admin
2. Click "Data Seeder" tab
3. Select a scenario (e.g., "Holiday Rush")
4. Click "Generate New" to create synthetic data
5. View progress in the Operation Log panel

## Scenario Selection

| Scenario | Best For |
|----------|----------|
| retail_standard | General development and testing |
| holiday_rush | Seasonal forecasting models |
| high_variance | Robustness testing |
| stockout_heavy | Inventory optimization |
| new_launches | Product launch forecasting |
| sparse | Gap handling validation |

## Verification

After generating data, run "Verify" to check:
- Foreign key integrity
- Non-negative constraints
- Date range coverage
- Unique constraint compliance
```

---

## SUCCESS CRITERIA

### Functional Requirements
- [ ] Status panel shows accurate row counts for all 7 tables
- [ ] Date range displays correctly (min/max from sales_daily)
- [ ] Generate button triggers full-new with selected scenario
- [ ] Delete button shows confirmation dialog before executing
- [ ] Append button adds data without affecting existing records
- [ ] Verify button runs all integrity checks
- [ ] Scenario selector updates generation parameters
- [ ] Configuration form validates input ranges

### UX Requirements
- [ ] Loading states shown during API calls
- [ ] Success/error toasts for all operations
- [ ] Progress indicator during long operations
- [ ] Disabled states for buttons during pending operations
- [ ] Responsive layout on tablet and mobile
- [ ] Keyboard accessible (focus states, enter to submit)

### Performance
- [ ] Status query returns in < 500ms
- [ ] UI remains responsive during generation
- [ ] No memory leaks from polling/subscriptions

### Safety
- [ ] Delete requires explicit confirmation
- [ ] Production environment check (SEEDER_ALLOW_PRODUCTION)
- [ ] Clear error messages for failed operations

---

## CROSS-MODULE INTEGRATION

| Direction | Module | Integration Point |
|-----------|--------|-------------------|
| **← Data Platform** | Phase 1 | Queries all 7 tables for status |
| **← Shared Seeder** | Phase 12 | Uses existing DataSeeder orchestrator |
| **→ Analytics** | Phase 7 | Invalidates KPI cache after generation |
| **→ Dashboard** | Phase 10 | Refreshes dashboard data after changes |
| **→ Explorer** | Phase 10 | New data appears in explorer tables |
| **→ Admin** | Phase 10 | Extends existing admin page with new tab |

---

## DOCUMENTATION LINKS

### shadcn/ui Components Used
- [Card](https://ui.shadcn.com/docs/components/card) — Container layout
- [Tabs](https://ui.shadcn.com/docs/components/tabs) — Admin panel navigation
- [Button](https://ui.shadcn.com/docs/components/button) — Action triggers
- [AlertDialog](https://ui.shadcn.com/docs/components/alert-dialog) — Destructive confirmations
- [Select](https://ui.shadcn.com/docs/components/select) — Scenario picker
- [Input](https://ui.shadcn.com/docs/components/input) — Configuration values
- [Progress](https://ui.shadcn.com/docs/components/progress) — Operation progress
- [Badge](https://ui.shadcn.com/docs/components/badge) — Status indicators
- [Skeleton](https://ui.shadcn.com/docs/components/skeleton) — Loading states
- [Accordion](https://ui.shadcn.com/docs/components/accordion) — Collapsible sections
- [Calendar](https://ui.shadcn.com/docs/components/calendar) — Date picker
- [Popover](https://ui.shadcn.com/docs/components/popover) — Date picker container

### TanStack
- [TanStack Query Mutations](https://tanstack.com/query/latest/docs/react/guides/mutations)
- [Query Invalidation](https://tanstack.com/query/latest/docs/react/guides/query-invalidation)

### Project References
- [CLAUDE.md](./CLAUDE.md) — Project coding standards
- [INITIAL-12.md](./INITIAL-12.md) — Data Seeder backend (The Forge)
- [docs/DATA-SEEDER.md](./docs/DATA-SEEDER.md) — Seeder documentation
- [app/shared/seeder/](./app/shared/seeder/) — Seeder implementation

---

## OTHER CONSIDERATIONS

### Best Practices

1. **Reuse Admin Patterns** — Follow existing RagSourcesPanel and AliasesPanel patterns
2. **Optimistic UI** — Show immediate feedback, rollback on error
3. **Cache Invalidation** — Invalidate analytics queries after data changes
4. **Feature Flag** — `VITE_ENABLE_SEEDER_PANEL` to hide in production

### Security

- **Production Guard** — Check `SEEDER_ALLOW_PRODUCTION` before any mutation
- **Confirmation Required** — AlertDialog for all destructive operations
- **Rate Limiting** — Prevent rapid repeated generation requests
- **Audit Logging** — Log all seeder operations with user context

### Observability

- **Structured Logging** — Log events: `seeder.generate_started`, `seeder.generate_completed`
- **Metrics** — Track generation duration, records created
- **Error Tracking** — Capture and display detailed error messages

### Future Enhancements

- WebSocket streaming for real-time progress
- YAML configuration editor
- Data preview (sample rows)
- Generation history with rollback
- Scheduled data refresh
- Multi-tenant isolation

---

## IMPLEMENTATION ORDER

1. **Backend API** — Create `app/features/seeder/` feature slice with routes/schemas/service
2. **Frontend Hooks** — Add `hooks/use-seeder.ts` with TanStack Query
3. **Status Panel** — DataStatusCard component with row counts
4. **Quick Actions** — QuickActionsCard with generate/delete buttons
5. **Configuration** — ConfigurationCard with form inputs
6. **Operation Log** — OperationLogCard with progress display
7. **Admin Integration** — Add Seeder tab to existing admin page
8. **Verification** — VerifyResult display component
9. **Testing** — Unit tests for hooks and components
10. **Documentation** — Update README and add examples

---

*Phase 13: The Forge UI — Where developers interact with the data factory.*
