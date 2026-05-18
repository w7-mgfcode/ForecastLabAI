# INITIAL-11B.md — ForecastLab Dashboard (The Face)

> **Part B of 3**: Architecture & Features
> See also: [INITIAL-11A.md](./INITIAL-11A.md) (Setup & Config) | [INITIAL-11C.md](./INITIAL-11C.md) (Pages & Components)

---

## Architectural Role

**"The Face"** — User interface, data visualization, and agent interaction using React 19 + shadcn/ui.

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
| Charts | [Recharts](https://recharts.org/) via shadcn/ui Chart | Time series visualization |
| Styling | Tailwind CSS 4 | Utility-first CSS |
| State | React 19 `use()` + TanStack Query | Server state management |

---

## App Shell Architecture

**Decision: Top Navigation + Tabs (Simple Implementation)**

Instead of a complex sidebar system, use a minimal top navigation bar with route-level tabs:

```
┌─────────────────────────────────────────────────────────────┐
│  [Logo] ForecastLab    [Dashboard] [Explorer] [Visualize]   │
│                        [Chat] [Admin]          [Theme] [?]  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [Page Content with optional Tabs for sub-routes]           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Desktop:** Top `navigation-menu` + route-level `tabs` where relevant
**Mobile:** `sheet` component for hamburger menu navigation

**shadcn components for App Shell:**
- `navigation-menu` — Main nav bar
- `sheet` — Mobile nav drawer
- `tabs` — Sub-route navigation (e.g., /explorer/sales vs /explorer/runs)
- `button` — Theme toggle, action buttons
- `dropdown-menu` — User menu, settings

---

## Features

### Data Explorer

Interactive data tables with full server-side capabilities:
- **Tables**: Sales, Stores, Products, Model Runs, Jobs
- **Features**: Pagination, sorting, filtering, column visibility
- **Export**: CSV download for selected/all rows
- **Pattern**: [shadcn/ui Data Table](https://ui.shadcn.com/docs/components/data-table)

**shadcn components:**
- `table` (Table, TableHeader, TableBody, TableRow, TableCell, TableHead)
- `checkbox` — Row selection
- `dropdown-menu` — Column visibility, row actions
- `input` — Filter inputs
- `select` — Filter dropdowns
- `button` — Pagination, export actions
- `badge` — Status columns
- `skeleton` — Loading rows

### Time Series Visualizers

Charts for forecasting analysis:
- **Actual vs Predicted**: Line chart with confidence intervals
- **Backtest Folds**: Train/test split visualization
- **Metric Comparison**: Bar charts for model comparison
- **Interactive**: Tooltips, zoom, pan, brush selection

**shadcn components:**
- `chart` (ChartContainer, ChartTooltip, ChartTooltipContent, ChartConfig)
- `card` — Chart wrapper with header/footer
- `select` — Chart controls (store, product, model)
- `badge` — Metric display
- `tabs` — Switch between chart views

### Agent Chat Interface

Real-time interaction with AI agents:
- **Streaming**: WebSocket-based token streaming
- **Citations**: Rendered with source links
- **Tool Calls**: Collapsible visualization of agent actions
- **History**: Session sidebar with conversation threads

**shadcn components:**
- `card` — Message bubbles
- `scroll-area` — Chat message list
- `collapsible` — Tool call details
- `accordion` — Citation groups
- `textarea` — Message input
- `button` — Send button
- `badge` — Source type indicators
- `skeleton` — Streaming placeholder

### Admin Panel

System management and monitoring:
- **RAG Sources**: Index/delete documentation sources
- **Model Aliases**: Manage deployment aliases
- **Health Dashboard**: Service status, recent errors
- **Job Monitor**: Active and historical job status

**shadcn components:**
- `card` — Section containers
- `table` — Source/alias/job lists
- `alert-dialog` — Delete confirmations
- `dialog` — Create/edit modals
- `badge` — Status indicators
- `progress` — Job progress
- `sonner` — Action feedback toasts

---

## shadcn/ui Components Summary

### Layout & Navigation
| Component | Usage |
|-----------|-------|
| `tabs` | Route-level section switching |
| `navigation-menu` | Top navigation bar |
| `sheet` | Mobile navigation drawer |
| `card` | Content containers, KPI cards |
| `scroll-area` | Scrollable content areas |
| `separator` | Visual dividers |

### Data Display
| Component | Usage |
|-----------|-------|
| `table` | Data table primitives |
| `badge` | Status indicators (SUCCESS, FAILED, PENDING) |
| `skeleton` | Loading placeholders |
| `pagination` | Table pagination controls |
| `progress` | Progress bars |

### Forms & Inputs
| Component | Usage |
|-----------|-------|
| `button` | Action buttons with variants |
| `input` | Text inputs |
| `select` | Dropdown selects |
| `textarea` | Multiline inputs |
| `calendar` | Date picker |
| `popover` | Date range picker wrapper |
| `checkbox` | Row selection in tables |

### Feedback & Overlays
| Component | Usage |
|-----------|-------|
| `sonner` | Toast notifications |
| `tooltip` | Hover hints |
| `alert-dialog` | Confirmation dialogs |
| `dialog` | Modal dialogs |

### Interactive
| Component | Usage |
|-----------|-------|
| `collapsible` | Tool call/citation sections |
| `accordion` | Expandable content groups |
| `dropdown-menu` | Action menus, column visibility |

### Charts
| Component | Usage |
|-----------|-------|
| `chart` | ChartContainer, ChartTooltip (wraps Recharts) |

---

## Cross-Module Integration

| Direction | Module | Integration Point |
|-----------|--------|-------------------|
| **← RAG Layer** | INITIAL-9 | Displays indexed sources, allows re-indexing |
| **← Agentic Layer** | INITIAL-10 | Chat interface, experiment status display |
| **← Registry** | Phase 6 | Run leaderboard, comparison views |
| **← Analytics** | Phase 7 | KPI dashboard, drilldown charts |
| **← Jobs** | Phase 7 | Job status monitoring |
| **← Dimensions** | Phase 7 | Store/product selectors |

---

## Success Criteria

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

## Other Considerations

- **No Hardcoded URLs**: API base URL from environment variable only
- **Error Boundaries**: Graceful error handling with retry options
- **Loading States**: Skeleton components for all async data
- **Optimistic Updates**: Instant UI feedback for mutations
- **Caching**: TanStack Query manages cache invalidation
- **Bundle Size**: Code splitting per route for fast initial load

---

## Documentation Links

- [shadcn/ui Documentation](https://ui.shadcn.com/)
- [shadcn/ui Data Table](https://ui.shadcn.com/docs/components/data-table)
- [shadcn/ui Charts](https://ui.shadcn.com/docs/components/chart)
- [TanStack Table](https://tanstack.com/table/latest)
- [TanStack Query](https://tanstack.com/query/latest)
- [Recharts](https://recharts.org/)
- [Vite Documentation](https://vite.dev/)
- [React 19 Documentation](https://react.dev/)
- [Tailwind CSS 4](https://tailwindcss.com/)
