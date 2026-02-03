# PRP-13: Data Seeder Dashboard (The Forge UI)

**Phase**: 13
**Status**: Ready for Implementation
**PRP Score**: 9/10 (High confidence for one-pass implementation)
**Estimated Complexity**: Medium

---

## Goal

Build the frontend admin interface for The Forge data seeder - a dashboard panel that allows users to:
1. View current database state (row counts for all 7 tables, date ranges)
2. Generate new synthetic datasets with scenario presets
3. Append data to existing datasets
4. Delete data with scope selection
5. Run data integrity verification

The backend API already exists at `/seeder/*` endpoints - this PRP focuses exclusively on the **frontend implementation**.

---

## Why

- **Developer Experience**: Provides visual interface for synthetic data operations instead of CLI
- **Testing Workflow**: Quick data generation for development and testing scenarios
- **Integration**: Extends existing Admin panel with consistent UI patterns
- **Safety**: Built-in confirmations for destructive operations, dry-run previews

---

## What

### User-Visible Behavior

1. New "Data Seeder" tab in Admin panel (`/admin`)
2. Status cards showing row counts for stores, products, calendar, sales, inventory, price_history, promotions
3. Date range display (earliest to latest sales date)
4. Scenario dropdown with 6 presets: retail_standard, holiday_rush, high_variance, stockout_heavy, new_launches, sparse
5. Action buttons: Generate, Append, Delete, Verify
6. Configuration form: seed, stores, products, dates, sparsity
7. AlertDialog confirmations for destructive actions
8. Loading states, success/error toasts

### Success Criteria

- [ ] Status panel displays all 7 table counts correctly
- [ ] Date range shows min/max from sales_daily (or "No data" when empty)
- [ ] Scenario selector lists 6 presets with descriptions
- [ ] Generate button creates dataset with selected scenario and config
- [ ] Delete button shows AlertDialog confirmation before executing
- [ ] Verify button runs integrity checks and displays results
- [ ] Loading spinners shown during API operations
- [ ] Toast notifications on success/error
- [ ] Tab integrates seamlessly with existing RAG Sources and Aliases tabs
- [ ] All TypeScript types are correct (no `any`)
- [ ] ESLint passes with no errors

---

## All Needed Context

### Documentation & References

```yaml
# MUST READ - Existing Patterns to Follow
- file: frontend/src/pages/admin.tsx
  why: Pattern for admin tabs, RagSourcesPanel and AliasesPanel show exact component structure

- file: frontend/src/hooks/use-runs.ts
  why: TanStack Query patterns for useQuery and useMutation with cache invalidation

- file: frontend/src/hooks/use-rag-sources.ts
  why: Mutation pattern with refetch, shows useIndexDocument pattern

- file: frontend/src/lib/api.ts
  why: API client usage - api<T>(endpoint, config)

- file: frontend/src/types/api.ts
  why: Type definition patterns, add seeder types here

# Backend API Reference (already implemented)
- file: app/features/seeder/schemas.py
  why: Exact response shapes - SeederStatus, ScenarioInfo, GenerateResult, DeleteResult, VerifyResult

- file: app/features/seeder/routes.py
  why: API endpoint signatures and HTTP methods/status codes

# shadcn/ui Components (all already installed)
- url: https://ui.shadcn.com/docs/components/tabs
  why: Tab structure pattern

- url: https://ui.shadcn.com/docs/components/card
  why: Status cards, configuration panels

- url: https://ui.shadcn.com/docs/components/alert-dialog
  why: Destructive action confirmation

- url: https://ui.shadcn.com/docs/components/select
  why: Scenario picker

- url: https://ui.shadcn.com/docs/components/input
  why: Configuration form inputs

- url: https://ui.shadcn.com/docs/components/badge
  why: Status indicators

- url: https://ui.shadcn.com/docs/components/calendar
  why: Date picker in Popover

- url: https://ui.shadcn.com/docs/components/progress
  why: Operation progress indicator
```

### Current Codebase Tree (Frontend Focus)

```bash
frontend/src/
├── App.tsx                      # Routes - no changes needed
├── components/
│   ├── common/
│   │   ├── error-display.tsx    # ErrorDisplay component to reuse
│   │   └── loading-state.tsx    # LoadingState component to reuse
│   └── ui/                      # 26 shadcn/ui components (all needed are installed)
│       ├── alert-dialog.tsx
│       ├── badge.tsx
│       ├── button.tsx
│       ├── calendar.tsx
│       ├── card.tsx
│       ├── checkbox.tsx
│       ├── collapsible.tsx
│       ├── dialog.tsx
│       ├── input.tsx
│       ├── popover.tsx
│       ├── progress.tsx
│       ├── select.tsx
│       ├── skeleton.tsx
│       ├── sonner.tsx
│       └── tabs.tsx
├── hooks/
│   ├── index.ts                 # Export all hooks - ADD use-seeder export
│   ├── use-runs.ts              # Pattern: useQuery/useMutation with cache invalidation
│   └── use-rag-sources.ts       # Pattern: mutations with refetch
├── lib/
│   └── api.ts                   # api<T> function
├── pages/
│   └── admin.tsx                # ADD SeederPanel to Tabs
└── types/
    └── api.ts                   # ADD seeder types
```

### Desired Codebase Tree (New/Modified Files)

```bash
frontend/src/
├── hooks/
│   ├── index.ts                 # MODIFY: Add 'export * from './use-seeder''
│   └── use-seeder.ts            # CREATE: TanStack Query hooks for seeder API
├── pages/
│   └── admin.tsx                # MODIFY: Add SeederPanel tab
└── types/
    └── api.ts                   # MODIFY: Add Seeder* type interfaces
```

### Known Gotchas & Library Quirks

```typescript
// CRITICAL: TanStack Query v5 patterns
// useMutation uses isPending (not isLoading)
const mutation = useMutation({ mutationFn: ... })
mutation.isPending  // ✅ correct in v5
mutation.isLoading  // ❌ deprecated

// CRITICAL: API client returns Promise<T>, not { data: T }
const data = await api<SeederStatus>('/seeder/status')  // ✅
// data is directly the response, not wrapped

// CRITICAL: DELETE with body requires special handling
// Our api() function supports body in DELETE:
api<DeleteResult>('/seeder/data', {
  method: 'DELETE',
  body: { scope: 'all', dry_run: false }
})

// CRITICAL: Date handling for API
// Backend expects date format: YYYY-MM-DD (ISO date string)
// Use format(date, 'yyyy-MM-dd') from date-fns

// CRITICAL: POST returns 201 for /generate and /append
// The api() function handles this transparently

// CRITICAL: void queryClient.invalidateQueries()
// Always use void prefix to satisfy TypeScript/ESLint for floating promises
```

---

## Implementation Blueprint

### Data Models (TypeScript Types)

Add to `frontend/src/types/api.ts`:

```typescript
// === Seeder ===
export interface SeederStatus {
  stores: number
  products: number
  calendar: number
  sales: number
  inventory: number
  price_history: number
  promotions: number
  date_range_start: string | null  // ISO date "2024-01-01"
  date_range_end: string | null
  last_updated: string | null      // ISO datetime
}

export interface ScenarioInfo {
  name: string
  description: string
  stores: number
  products: number
  start_date: string  // ISO date
  end_date: string
}

export interface GenerateParams {
  scenario?: string        // default: "retail_standard"
  seed?: number           // default: 42
  stores?: number         // 1-100, default: 10
  products?: number       // 1-500, default: 50
  start_date?: string     // ISO date
  end_date?: string
  sparsity?: number       // 0.0-1.0
  dry_run?: boolean
}

export interface AppendParams {
  start_date: string      // Required
  end_date: string        // Required
  seed?: number
}

export interface DeleteParams {
  scope?: 'all' | 'facts' | 'dimensions'  // default: "all"
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
```

---

## Tasks (Implementation Order)

### Task 1: Add TypeScript Types
**MODIFY** `frontend/src/types/api.ts`
- FIND pattern: After the `// === Error Response (RFC 7807) ===` section
- ADD: All seeder interfaces before EOF

```typescript
// ADD these interfaces at the end of the file, before the closing empty line
// === Seeder ===
export interface SeederStatus { ... }
export interface ScenarioInfo { ... }
// ... (all types from Data Models section above)
```

### Task 2: Create Seeder Hooks
**CREATE** `frontend/src/hooks/use-seeder.ts`
- MIRROR pattern from: `frontend/src/hooks/use-runs.ts`
- Uses TanStack Query v5 patterns

```typescript
// frontend/src/hooks/use-seeder.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type {
  SeederStatus,
  ScenarioInfo,
  GenerateParams,
  GenerateResult,
  AppendParams,
  DeleteParams,
  DeleteResult,
  VerifyResult,
} from '@/types/api'

// Query: Get database status (row counts, date range)
export function useSeederStatus() {
  return useQuery({
    queryKey: ['seeder', 'status'],
    queryFn: () => api<SeederStatus>('/seeder/status'),
    // Refresh every 30 seconds to catch external changes
    refetchInterval: 30000,
  })
}

// Query: Get available scenarios (cached indefinitely - they don't change)
export function useSeederScenarios() {
  return useQuery({
    queryKey: ['seeder', 'scenarios'],
    queryFn: () => api<ScenarioInfo[]>('/seeder/scenarios'),
    staleTime: Infinity,
  })
}

// Mutation: Generate new dataset
export function useGenerateData() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (params: GenerateParams) =>
      api<GenerateResult>('/seeder/generate', { method: 'POST', body: params }),
    onSuccess: () => {
      // Invalidate status to refresh counts
      void queryClient.invalidateQueries({ queryKey: ['seeder', 'status'] })
      // Also invalidate analytics as data changed
      void queryClient.invalidateQueries({ queryKey: ['analytics'] })
      void queryClient.invalidateQueries({ queryKey: ['kpis'] })
    },
  })
}

// Mutation: Append data to existing dataset
export function useAppendData() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (params: AppendParams) =>
      api<GenerateResult>('/seeder/append', { method: 'POST', body: params }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['seeder', 'status'] })
      void queryClient.invalidateQueries({ queryKey: ['analytics'] })
      void queryClient.invalidateQueries({ queryKey: ['kpis'] })
    },
  })
}

// Mutation: Delete data
export function useDeleteData() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (params: DeleteParams) =>
      api<DeleteResult>('/seeder/data', { method: 'DELETE', body: params }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['seeder', 'status'] })
      void queryClient.invalidateQueries({ queryKey: ['analytics'] })
      void queryClient.invalidateQueries({ queryKey: ['kpis'] })
    },
  })
}

// Mutation: Verify data integrity
export function useVerifyData() {
  return useMutation({
    mutationFn: () => api<VerifyResult>('/seeder/verify', { method: 'POST' }),
  })
}
```

### Task 3: Export Seeder Hooks
**MODIFY** `frontend/src/hooks/index.ts`
- ADD export line

```typescript
// ADD this line at the end of the file
export * from './use-seeder'
```

### Task 4: Add SeederPanel to Admin Page
**MODIFY** `frontend/src/pages/admin.tsx`

This is the main implementation task. Follow the exact pattern of RagSourcesPanel and AliasesPanel.

#### 4a: Add Imports (at top of file)

```typescript
// ADD to existing imports
import { format } from 'date-fns'
import {
  Flame,       // Generate icon
  Plus,        // Append icon
  CheckCircle, // Verify icon
  RefreshCw,   // Refresh icon
  Store,       // Stats icon
  Package,     // Stats icon
  Calendar,    // Stats icon
  TrendingUp,  // Stats icon (sales)
  Warehouse,   // Stats icon (inventory)
  History,     // Stats icon (price history)
  Percent,     // Stats icon (promotions)
} from 'lucide-react'
import {
  useSeederStatus,
  useSeederScenarios,
  useGenerateData,
  useDeleteData,
  useVerifyData,
} from '@/hooks/use-seeder'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Progress } from '@/components/ui/progress'
import { toast } from 'sonner'
import type {
  ScenarioInfo,
  VerifyCheck,
  VerifyCheckStatus,
} from '@/types/api'
```

#### 4b: Add Tab to AdminPage Component

```tsx
// MODIFY the Tabs component - ADD new TabsTrigger and TabsContent
<Tabs defaultValue="rag">
  <TabsList>
    <TabsTrigger value="rag">
      <Database className="h-4 w-4 mr-2" />
      RAG Sources
    </TabsTrigger>
    <TabsTrigger value="aliases">
      <Tag className="h-4 w-4 mr-2" />
      Deployment Aliases
    </TabsTrigger>
    {/* ADD THIS NEW TAB */}
    <TabsTrigger value="seeder">
      <Flame className="h-4 w-4 mr-2" />
      Data Seeder
    </TabsTrigger>
  </TabsList>

  <TabsContent value="rag" className="mt-6">
    <RagSourcesPanel />
  </TabsContent>

  <TabsContent value="aliases" className="mt-6">
    <AliasesPanel />
  </TabsContent>

  {/* ADD THIS NEW TAB CONTENT */}
  <TabsContent value="seeder" className="mt-6">
    <SeederPanel />
  </TabsContent>
</Tabs>
```

#### 4c: Create SeederPanel Component (new function in same file)

```tsx
function SeederPanel() {
  const { data: status, isLoading, error, refetch } = useSeederStatus()
  const { data: scenarios } = useSeederScenarios()
  const generateMutation = useGenerateData()
  const deleteMutation = useDeleteData()
  const verifyMutation = useVerifyData()

  const [selectedScenario, setSelectedScenario] = useState('retail_standard')
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [verifyResult, setVerifyResult] = useState<{
    passed: boolean
    checks: VerifyCheck[]
    passed_count: number
    warning_count: number
    failed_count: number
  } | null>(null)

  const handleGenerate = async () => {
    try {
      const result = await generateMutation.mutateAsync({
        scenario: selectedScenario,
      })
      toast.success(`Generated ${result.records_created.sales?.toLocaleString() ?? 0} sales records in ${result.duration_seconds.toFixed(1)}s`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Generation failed')
    }
  }

  const handleDelete = async () => {
    try {
      const result = await deleteMutation.mutateAsync({ scope: 'all' })
      setDeleteDialogOpen(false)
      toast.success(result.message)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Delete failed')
    }
  }

  const handleVerify = async () => {
    try {
      const result = await verifyMutation.mutateAsync()
      setVerifyResult(result)
      if (result.passed) {
        toast.success('All integrity checks passed')
      } else {
        toast.warning(`${result.failed_count} checks failed`)
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Verification failed')
    }
  }

  if (error) {
    return <ErrorDisplay error={error} onRetry={refetch} />
  }

  return (
    <div className="space-y-6">
      {/* Status Card */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Current Data Summary</CardTitle>
            <CardDescription>
              {status?.date_range_start && status?.date_range_end
                ? `${status.date_range_start} → ${status.date_range_end}`
                : 'No data yet'}
            </CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="grid grid-cols-7 gap-4">
              {Array.from({ length: 7 }).map((_, i) => (
                <Skeleton key={i} className="h-20" />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-7 gap-4">
              <StatCard icon={Store} label="Stores" value={status?.stores ?? 0} />
              <StatCard icon={Package} label="Products" value={status?.products ?? 0} />
              <StatCard icon={Calendar} label="Calendar" value={status?.calendar ?? 0} />
              <StatCard icon={TrendingUp} label="Sales" value={status?.sales ?? 0} />
              <StatCard icon={Warehouse} label="Inventory" value={status?.inventory ?? 0} />
              <StatCard icon={History} label="Prices" value={status?.price_history ?? 0} />
              <StatCard icon={Percent} label="Promos" value={status?.promotions ?? 0} />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Actions Card */}
      <Card>
        <CardHeader>
          <CardTitle>Quick Actions</CardTitle>
          <CardDescription>Generate, delete, or verify synthetic data</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-2 flex-wrap">
            <Button
              onClick={handleGenerate}
              disabled={generateMutation.isPending}
            >
              {generateMutation.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Flame className="h-4 w-4 mr-2" />
              )}
              Generate New
            </Button>

            <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
              <AlertDialogTrigger asChild>
                <Button
                  variant="destructive"
                  disabled={deleteMutation.isPending || (status?.sales ?? 0) === 0}
                >
                  {deleteMutation.isPending ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Trash2 className="h-4 w-4 mr-2" />
                  )}
                  Delete All
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete All Data?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will permanently delete all {status?.sales?.toLocaleString() ?? 0} sales records,
                    {' '}{status?.stores ?? 0} stores, and {status?.products ?? 0} products.
                    This action cannot be undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={handleDelete}>
                    Delete All Data
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>

            <Button
              variant="outline"
              onClick={handleVerify}
              disabled={verifyMutation.isPending || (status?.sales ?? 0) === 0}
            >
              {verifyMutation.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <CheckCircle className="h-4 w-4 mr-2" />
              )}
              Verify
            </Button>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Scenario</label>
            <Select value={selectedScenario} onValueChange={setSelectedScenario}>
              <SelectTrigger className="w-[300px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {scenarios?.map((s: ScenarioInfo) => (
                  <SelectItem key={s.name} value={s.name}>
                    <div className="flex flex-col">
                      <span>{formatScenarioLabel(s.name)}</span>
                      <span className="text-xs text-muted-foreground">{s.description}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Verification Results */}
      {verifyResult && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              Verification Results
              <Badge variant={verifyResult.passed ? 'default' : 'destructive'}>
                {verifyResult.passed ? 'Passed' : 'Failed'}
              </Badge>
            </CardTitle>
            <CardDescription>
              {verifyResult.passed_count} passed • {verifyResult.warning_count} warnings • {verifyResult.failed_count} failed
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {verifyResult.checks.map((check: VerifyCheck, idx: number) => (
                <div key={idx} className="flex items-center justify-between py-2 border-b last:border-0">
                  <div>
                    <p className="font-medium">{check.name}</p>
                    <p className="text-xs text-muted-foreground">{check.message}</p>
                  </div>
                  <Badge variant={getCheckBadgeVariant(check.status)}>
                    {check.status}
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// Helper component for stat cards
function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: number
}) {
  return (
    <div className="text-center p-3 rounded-lg bg-muted">
      <Icon className="h-4 w-4 mx-auto mb-1 text-muted-foreground" />
      <p className="text-lg font-bold">{value.toLocaleString()}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  )
}

// Helper for scenario names
function formatScenarioLabel(name: string): string {
  return name
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

// Helper for badge variants
function getCheckBadgeVariant(status: VerifyCheckStatus): 'default' | 'secondary' | 'destructive' {
  switch (status) {
    case 'passed':
      return 'default'
    case 'warning':
      return 'secondary'
    case 'failed':
      return 'destructive'
  }
}
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
# Run from frontend/ directory
cd frontend

# TypeScript check
pnpm tsc --noEmit

# ESLint check
pnpm lint

# Expected: No errors
```

### Level 2: Build Check

```bash
# Build production bundle
pnpm build

# Expected: Build succeeds without errors
```

### Level 3: Integration Test (Manual)

```bash
# Terminal 1: Start backend
cd /home/w7-shellsnake/w7-DEV_X1/w7-ForecastLabAI
uv run uvicorn app.main:app --reload --port 8123

# Terminal 2: Start frontend
cd frontend
pnpm dev

# Test in browser:
# 1. Navigate to http://localhost:5173/admin
# 2. Click "Data Seeder" tab
# 3. Verify status cards show (0 or existing counts)
# 4. Select "Holiday Rush" scenario
# 5. Click "Generate New"
# 6. Wait for completion, verify toast appears
# 7. Verify status cards update with new counts
# 8. Click "Verify" - verify results display
# 9. Click "Delete All" - confirm dialog appears
# 10. Cancel, then try again and confirm
# 11. Verify counts reset to 0
```

### Level 4: API Verification

```bash
# Test endpoints directly
curl http://localhost:8123/seeder/status | jq
curl http://localhost:8123/seeder/scenarios | jq

# Expected: JSON responses matching SeederStatus and ScenarioInfo[] types
```

---

## Final Validation Checklist

- [ ] `pnpm tsc --noEmit` passes (no TypeScript errors)
- [ ] `pnpm lint` passes (no ESLint errors)
- [ ] `pnpm build` succeeds
- [ ] Data Seeder tab appears in Admin panel
- [ ] Status cards display row counts correctly
- [ ] Scenario dropdown shows 6 presets with descriptions
- [ ] Generate button works with loading state
- [ ] Delete shows confirmation dialog
- [ ] Verify displays check results with badges
- [ ] Toast notifications appear on success/error
- [ ] No console errors in browser DevTools

---

## Anti-Patterns to Avoid

- ❌ Don't use `any` type - all types are defined
- ❌ Don't use `isLoading` on mutations - use `isPending` (TanStack Query v5)
- ❌ Don't forget `void` prefix on `queryClient.invalidateQueries()`
- ❌ Don't create separate component files - follow existing admin.tsx pattern
- ❌ Don't add new routes - SeederPanel goes inside existing admin page
- ❌ Don't skip AlertDialog for delete - always confirm destructive actions
- ❌ Don't forget toast imports from 'sonner'

---

## Cross-Module Integration

| Direction | Module | Integration Point |
|-----------|--------|-------------------|
| **← Backend** | Phase 12 | Uses existing `/seeder/*` REST endpoints |
| **← Admin** | Phase 10 | Extends existing admin.tsx with new tab |
| **→ Analytics** | Phase 7 | Invalidates KPI/analytics cache after data changes |
| **← Types** | Common | Adds types to shared api.ts |

---

## Files Changed Summary

| File | Action | Lines Changed |
|------|--------|---------------|
| `frontend/src/types/api.ts` | MODIFY | +50 lines (seeder types) |
| `frontend/src/hooks/use-seeder.ts` | CREATE | ~70 lines |
| `frontend/src/hooks/index.ts` | MODIFY | +1 line (export) |
| `frontend/src/pages/admin.tsx` | MODIFY | +200 lines (SeederPanel) |

**Total**: ~320 lines of new/modified code

---

*PRP-13: The Forge UI - Visual control for synthetic data generation*
