# PRP-11C: ForecastLab Dashboard — Validation & Testing

**Feature**: INITIAL-11C.md — Pages & Components Validation
**Status**: Ready for Validation
**Confidence Score**: 9/10
**Prerequisites**: PRP-11A (Setup) ✅ COMPLETED, PRP-11B (Architecture) ✅ COMPLETED

---

## Goal

Validate and test the existing ForecastLab Dashboard implementation against INITIAL-11C.md specifications:

1. **Verify all routes render correctly** with no console errors
2. **Test server-side pagination** on all DataTable pages
3. **Validate chart components** render with mock data
4. **Test WebSocket chat** connection and message flow
5. **Verify responsive design** on mobile viewports
6. **Run type checking and linting** to ensure code quality
7. **Test dark/light theme** toggle and persistence
8. **Validate accessibility** (keyboard navigation, screen reader support)

---

## Why

- **Quality Assurance**: Confirm implementation matches INITIAL-11C specifications
- **Regression Prevention**: Establish baseline tests for future changes
- **Integration Verification**: Ensure frontend correctly integrates with backend API
- **User Experience**: Validate responsive design and accessibility

---

## What

### Implementation Status

All pages and components from INITIAL-11C.md have been implemented:

| Route | Status | Component |
|-------|--------|-----------|
| `/` | ✅ | DashboardPage with KPIs |
| `/explorer/sales` | ✅ | Sales drilldowns with tabs |
| `/explorer/stores` | ✅ | Store DataTable |
| `/explorer/products` | ✅ | Product DataTable |
| `/explorer/runs` | ✅ | Model runs DataTable |
| `/explorer/jobs` | ✅ | Jobs monitor |
| `/visualize/forecast` | ✅ | Forecast TimeSeriesChart |
| `/visualize/backtest` | ✅ | Backtest folds chart |
| `/chat` | ✅ | Agent chat with WebSocket |
| `/admin` | ✅ | RAG sources & aliases |

### Components Implemented

| Component | Location | Status |
|-----------|----------|--------|
| DataTable | `components/data-table/data-table.tsx` | ✅ |
| DataTableToolbar | `components/data-table/data-table-toolbar.tsx` | ✅ |
| DataTablePagination | `components/data-table/data-table-pagination.tsx` | ✅ |
| TimeSeriesChart | `components/charts/time-series-chart.tsx` | ✅ |
| BacktestFoldsChart | `components/charts/backtest-folds-chart.tsx` | ✅ |
| KPICard | `components/charts/kpi-card.tsx` | ✅ |
| ChatMessage | `components/chat/chat-message.tsx` | ✅ |
| ChatInput | `components/chat/chat-input.tsx` | ✅ |
| ToolCallDisplay | `components/chat/tool-call-display.tsx` | ✅ |
| DateRangePicker | `components/common/date-range-picker.tsx` | ✅ |
| StatusBadge | `components/common/status-badge.tsx` | ✅ |
| ErrorDisplay | `components/common/error-display.tsx` | ✅ |
| LoadingState | `components/common/loading-state.tsx` | ✅ |
| AppShell | `components/layout/app-shell.tsx` | ✅ |
| TopNav | `components/layout/top-nav.tsx` | ✅ |
| ThemeToggle | `components/layout/theme-toggle.tsx` | ✅ |

### Success Criteria

- [ ] `pnpm build` succeeds with no errors
- [ ] `pnpm lint` passes with no errors
- [ ] `pnpm tsc --noEmit` passes with no type errors
- [ ] All 10 routes render without console errors
- [ ] DataTable pagination works (page navigation, page size)
- [ ] Filters work on Model Runs page (status, model type)
- [ ] DateRangePicker updates Dashboard and Sales explorer
- [ ] TimeSeriesChart renders with sample data
- [ ] BacktestFoldsChart renders fold metrics
- [ ] Chat page establishes WebSocket connection
- [ ] Theme toggle persists across page refresh
- [ ] Mobile navigation sheet opens and closes
- [ ] All interactive elements are keyboard accessible

---

## All Needed Context

### Documentation & References

```yaml
# Validation Resources
- file: frontend/README.md
  why: "Complete documentation of implemented features"

- file: frontend/src/App.tsx
  why: "Route configuration and lazy loading setup"

- file: frontend/src/lib/constants.ts
  why: "Route paths and navigation items"

- file: frontend/src/types/api.ts
  why: "API response types for validation"

# INITIAL-11C Specification
- file: INITIAL-11C.md
  why: "Original specification for validation checklist"

# Backend API for Integration Testing
- url: http://localhost:8123/docs
  why: "API documentation for endpoint verification"
```

### Current Codebase Tree (Frontend)

```bash
frontend/
├── src/
│   ├── components/
│   │   ├── charts/              # KPICard, TimeSeriesChart, BacktestFoldsChart
│   │   ├── chat/                # ChatMessage, ChatInput, ToolCallDisplay
│   │   ├── common/              # DateRangePicker, StatusBadge, ErrorDisplay
│   │   ├── data-table/          # DataTable, DataTableToolbar, Pagination
│   │   ├── layout/              # AppShell, TopNav, ThemeToggle
│   │   └── ui/                  # 26 shadcn/ui components
│   ├── hooks/                   # use-stores, use-products, use-kpis, etc.
│   ├── lib/                     # api.ts, constants.ts, utils.ts
│   ├── pages/
│   │   ├── explorer/            # stores, products, runs, jobs, sales
│   │   ├── visualize/           # forecast, backtest
│   │   ├── dashboard.tsx
│   │   ├── chat.tsx
│   │   └── admin.tsx
│   ├── providers/               # theme-provider.tsx
│   └── types/                   # api.ts (TypeScript types)
├── components.json              # shadcn/ui config
├── package.json
└── vite.config.ts
```

### Known Gotchas & Library Quirks

```typescript
// CRITICAL: API pagination is 1-indexed
// Frontend uses 0-indexed pagination state, must convert:
// page: pagination.pageIndex + 1 (API request)
// pagination.pageIndex = page - 1 (from API response)

// CRITICAL: TanStack Query v5 uses keepPreviousData function
import { keepPreviousData } from '@tanstack/react-query'
// NOT: import { keepPreviousData } from 'react-query' (v3)

// CRITICAL: Tailwind CSS 4 uses @import not @tailwind
// In index.css: @import 'tailwindcss';
// NOT: @tailwind base; @tailwind components; etc.

// CRITICAL: WebSocket URL must match backend
// Default: ws://localhost:8123/agents/stream
// Set via: VITE_WS_URL environment variable

// CRITICAL: shadcn/ui chart requires ChartConfig
// Always define chartConfig with colors matching CSS variables
```

---

## Implementation Blueprint

### Task 1: Build & Type Validation

Verify the codebase compiles without errors.

```bash
# Run in frontend/ directory
cd frontend

# Step 1: Clean install dependencies
rm -rf node_modules pnpm-lock.yaml
pnpm install

# Step 2: Type check (strict mode)
pnpm tsc --noEmit

# Step 3: Lint check
pnpm lint

# Step 4: Production build
pnpm build

# Expected: All commands succeed with exit code 0
```

### Task 2: Route Rendering Validation

Manually verify each route renders correctly.

```bash
# Start dev server
pnpm dev

# Open browser to http://localhost:5173
# Navigate to each route and check:
# 1. No console errors
# 2. Page content renders
# 3. Loading states show during data fetch
# 4. Error states show for API failures

# Test sequence:
# 1. / (Dashboard) - KPI cards, top stores/products
# 2. /explorer/sales - Tabs for dimension switching
# 3. /explorer/stores - DataTable with pagination
# 4. /explorer/products - DataTable with search
# 5. /explorer/runs - DataTable with filters
# 6. /explorer/jobs - Job monitor table
# 7. /visualize/forecast - Job ID input, chart
# 8. /visualize/backtest - Job ID input, fold chart
# 9. /chat - Session creation, message input
# 10. /admin - RAG sources, aliases tabs
```

### Task 3: DataTable Pagination Testing

Verify server-side pagination on DataTable pages.

```typescript
// Test on /explorer/runs page:

// 1. Verify page indicator shows "Page 1 of X"
// 2. Click "Next" - verify page changes
// 3. Click "Previous" - verify returns to page 1
// 4. Change page size dropdown - verify data refreshes
// 5. Apply filter - verify pagination resets to page 1
// 6. Click "Reset" - verify filters clear

// Expected behavior:
// - Page size default: 25
// - Pagination controls disabled when on first/last page
// - Loading skeleton shows during page transitions
```

### Task 4: Chart Component Testing

Verify chart components render correctly.

```typescript
// Test TimeSeriesChart (/visualize/forecast):
// 1. Enter a valid job ID
// 2. Verify chart renders with predicted line
// 3. Hover over data points - verify tooltip
// 4. Check legend shows "Predicted"

// Test BacktestFoldsChart (/visualize/backtest):
// 1. Enter a valid backtest job ID
// 2. Verify bar chart renders for MAE
// 3. Switch to sMAPE tab - verify chart updates
// 4. Switch to WAPE, Bias tabs
// 5. Verify MetricsSummary displays aggregated values

// Test KPICard (Dashboard):
// 1. Verify 4 KPI cards render
// 2. Verify loading skeleton during fetch
// 3. Verify values update on date range change
```

### Task 5: WebSocket Chat Testing

Verify chat interface and WebSocket connection.

```typescript
// Prerequisites: Backend must be running with agents endpoint

// Test sequence:
// 1. Navigate to /chat
// 2. Select agent type (RAG Assistant)
// 3. Click "Start Session" - verify WebSocket connects
// 4. Status shows "Connected" in green
// 5. Type message, press Enter or click Send
// 6. User message appears in chat
// 7. Streaming response appears with typing indicator
// 8. Final message shows with citations (if any)
// 9. Click "New Session" - verify session resets

// Error cases:
// - Backend not running: should show "disconnected" status
// - Network error: should show reconnection attempts
```

### Task 6: Theme Toggle Testing

Verify dark/light mode toggle.

```typescript
// Test sequence:
// 1. Click theme toggle button (top-right)
// 2. Verify theme changes (light → dark)
// 3. Refresh page - verify theme persists
// 4. Click toggle again - verify returns to light
// 5. Check localStorage for "theme" key

// Visual checks:
// - Background color changes
// - Text color remains readable
// - Chart colors adjust for dark mode
// - Borders and cards adapt
```

### Task 7: Responsive Design Testing

Verify mobile responsiveness.

```typescript
// Using browser DevTools:
// 1. Resize to mobile width (375px)
// 2. Verify navigation collapses to hamburger menu
// 3. Click hamburger - Sheet opens from left
// 4. Navigate via Sheet - verify routes work
// 5. Click outside Sheet - verify it closes
// 6. Verify DataTable is scrollable horizontally
// 7. Verify charts resize appropriately
// 8. Verify DateRangePicker is usable on mobile
```

### Task 8: Accessibility Testing

Verify keyboard navigation and screen reader support.

```typescript
// Keyboard navigation:
// 1. Tab through navigation items
// 2. Enter to select, Escape to close dropdowns
// 3. Tab through DataTable rows
// 4. Use arrow keys in Select dropdowns
// 5. Enter to submit chat message

// Screen reader:
// 1. Buttons have aria-labels
// 2. Form inputs have associated labels
// 3. Status badges have appropriate text
// 4. Charts have accessibility layer (accessibilityLayer prop)
```

---

## Validation Loop

### Level 1: Build Validation

```bash
cd frontend

# Clean and reinstall
rm -rf node_modules dist
pnpm install

# Type check
pnpm tsc --noEmit
# Expected: No errors

# Lint
pnpm lint
# Expected: No errors

# Build
pnpm build
# Expected: Build succeeds, outputs to dist/
```

### Level 2: Visual Regression Testing

```bash
# Start dev server
pnpm dev

# Run through each route manually
# Document any visual issues or console errors

# Optional: Screenshot each page for comparison
# Use browser DevTools > Capture screenshot
```

### Level 3: Integration Testing (with Backend)

```bash
# Terminal 1: Start backend
cd /home/w7-shellsnake/w7-DEV_X1/w7-ForecastLabAI
docker-compose up -d
uv run uvicorn app.main:app --reload --port 8123

# Terminal 2: Start frontend
cd frontend
pnpm dev

# Test API integration:
# 1. Dashboard loads KPIs from /analytics/kpis
# 2. Explorer pages fetch paginated data
# 3. Admin page loads RAG sources
# 4. Chat connects to WebSocket

# Verify in Network tab:
# - API requests use correct endpoints
# - Responses are parsed correctly
# - Error responses show ErrorDisplay
```

### Level 4: Cross-Browser Testing

```bash
# Test in multiple browsers:
# - Chrome (primary)
# - Firefox
# - Safari (if available)
# - Edge

# Check for:
# - CSS rendering differences
# - WebSocket compatibility
# - LocalStorage persistence
```

---

## Final Validation Checklist

### Build & Types
- [ ] `pnpm install` completes without errors
- [ ] `pnpm tsc --noEmit` passes
- [ ] `pnpm lint` passes
- [ ] `pnpm build` succeeds

### Routes
- [ ] `/` (Dashboard) renders KPI cards
- [ ] `/explorer/sales` renders tabs and drilldowns
- [ ] `/explorer/stores` renders DataTable with pagination
- [ ] `/explorer/products` renders DataTable with search
- [ ] `/explorer/runs` renders DataTable with filters
- [ ] `/explorer/jobs` renders job monitor
- [ ] `/visualize/forecast` renders TimeSeriesChart
- [ ] `/visualize/backtest` renders BacktestFoldsChart
- [ ] `/chat` renders and connects WebSocket
- [ ] `/admin` renders RAG sources and aliases

### Components
- [ ] DataTable shows loading skeleton
- [ ] DataTable pagination changes pages
- [ ] DataTableToolbar filters work
- [ ] TimeSeriesChart renders with legends
- [ ] BacktestFoldsChart switches metrics
- [ ] ChatMessage shows citations
- [ ] DateRangePicker updates data
- [ ] StatusBadge shows correct variants
- [ ] ErrorDisplay shows on API errors
- [ ] LoadingState shows during fetches

### UX
- [ ] Theme toggle works (light ↔ dark)
- [ ] Theme persists on refresh
- [ ] Mobile navigation works
- [ ] Keyboard navigation works
- [ ] No console errors in production build

### API Integration (with backend running)
- [ ] Dashboard fetches KPIs
- [ ] Explorer pages paginate correctly
- [ ] Filters send correct query params
- [ ] WebSocket connects and streams
- [ ] Error responses display correctly

---

## Anti-Patterns to Avoid

- ❌ Don't skip build verification before testing
- ❌ Don't test only happy paths - test error states
- ❌ Don't ignore console warnings or errors
- ❌ Don't test only on desktop - verify mobile
- ❌ Don't skip keyboard navigation testing
- ❌ Don't assume backend is running - test offline state

---

## Validation Report Template

After completing validation, fill in this report:

```markdown
## Validation Report - INITIAL-11C

**Date**: YYYY-MM-DD
**Tester**: [Name]
**Build Version**: [git commit hash]

### Build Status
- Type Check: ✅ PASS / ❌ FAIL
- Lint: ✅ PASS / ❌ FAIL
- Build: ✅ PASS / ❌ FAIL

### Route Status
| Route | Renders | No Errors | Notes |
|-------|---------|-----------|-------|
| / | ✅/❌ | ✅/❌ | |
| /explorer/sales | ✅/❌ | ✅/❌ | |
| ... | | | |

### Component Status
| Component | Works | Notes |
|-----------|-------|-------|
| DataTable | ✅/❌ | |
| TimeSeriesChart | ✅/❌ | |
| ... | | |

### Issues Found
1. [Description] - [Severity: Critical/High/Medium/Low]
2. ...

### Recommendations
1. [Action item]
2. ...

### Overall Status: ✅ PASS / ❌ NEEDS FIXES
```

---

## Summary

This PRP provides a comprehensive validation framework for the INITIAL-11C implementation. All components and pages have been implemented. The validation tasks focus on:

1. **Build Integrity** - TypeScript, ESLint, production build
2. **Functional Testing** - Each route and component
3. **Integration Testing** - API and WebSocket connectivity
4. **UX Testing** - Responsiveness, accessibility, theming

Run through each task sequentially, documenting results in the validation report template. Any issues found should be logged as GitHub issues or fixed before marking validation complete.
