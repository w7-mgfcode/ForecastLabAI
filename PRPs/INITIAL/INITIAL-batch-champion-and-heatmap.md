# INITIAL-batch-champion-and-heatmap — Portfolio Champion Selection + Heatmap

**Author:** plan-feature agent (drafted 2026-05-20)
**Status:** `proposed`
**Depends on:** `batch-runner-mvp` (parent `batch_job` + child `batch_job_item` + `POST /batch/forecasting` — NOT YET BUILT; see `docs/optional-features/06-portfolio-forecasting-batch-runner.md` § "MVP Scope")
**Successor:** `PRPs/PRP-NN-batch-champion-and-heatmap.md` (to be authored)
**Source feature doc:** `docs/optional-features/06-portfolio-forecasting-batch-runner.md` § "Full Version" (items 4 + 5)

---

## Problem Statement

The MVP batch runner trains/backtests/predicts across many `(store_id, product_id)` pairs but stops at "the run succeeded; here is the per-item row." A portfolio operator's two next questions are immediate and tightly coupled:

1. **"Which model won for each series?"** — across `naive | seasonal_naive | moving_average | regression | lightgbm` (the model families wired up in `app/features/forecasting/service.py` / PRP-31), there is no batch-aware way to say "promote the best one per (store, product) to a stable alias."
2. **"How is forecast quality distributed across my portfolio?"** — a 50-store × 200-SKU batch produces 10,000 metric rows. Without a portfolio-level visualization, an operator cannot see which regions or categories are systematically worse — the data is locked behind a row-per-item table.

Both questions consume the **same aggregated surface** — `batch_job_item × model × (store, product)` rolled up by `WAPE / sMAPE / MAE / bias` — and ship together so the operator's loop "see the grid → spot the gap → promote the winners" closes inside one page. Splitting them creates two endpoints over the same SQL and two PRs that touch the same Pydantic schemas.

**Who is affected:** the portfolio operator persona introduced by the batch runner MVP. **Pain if unsolved:** the MVP table view is correct but un-actionable at portfolio scale; champion promotion has to be done one-alias-at-a-time via the existing `POST /registry/aliases`, which is what the MVP was meant to obviate.

---

## Goals

- **Primary (Champion Selection — gap-analysis V=5, the highest user value of the six Full-Version items):** A single operator action against a completed batch produces a *dry-run* list of proposed champion aliases per `(store_id, product_id)` and, on explicit confirmation, applies them via the existing `RegistryService.create_alias` mutation path.
- **Primary (Portfolio Heatmaps — V=4):** A single page renders the batch's metric surface as a `store × product` grid with selectable metric, drilldown on cell click, and a legend that names the color scale.
- **Secondary:**
  - One shared aggregation service powers both endpoints (no duplicated SQL).
  - Champion selection is *idempotent* — re-running on the same batch produces an empty diff.
  - HITL approval gates any agent-driven champion promotion (per `.claude/rules/security-patterns.md`).
- **Non-goals:**
  - Building or extending the MVP batch runner itself (separate INITIAL).
  - Heatmaps over arbitrary historical batches (current batch only — multi-batch comparison is a follow-up).
  - Real-time updates during a running batch (post-completion only).
  - CSV export — covered by the broader Full-Version item "Exportable results."
  - Champion-per-region or champion-per-category (single grain: `(store_id, product_id)`).
  - Replacing the existing `/registry/aliases` endpoint or its uniqueness constraint.

---

## Item 1 — Batch-Level Champion Selection

### Definition of "champion"

For each `(store_id, product_id)` pair that appears in `batch_job_item` rows with `status = success`:

1. **Primary key:** lowest `WAPE` across all model types that ran for that pair.
2. **First tie-break:** lowest `sMAPE`.
3. **Second tie-break:** earliest `model_run.created_at` (deterministic — the run that finished first wins, so re-runs don't flip the verdict).
4. **Exclusion:** any model row with NaN WAPE (e.g., zero-actuals fold) is dropped from the candidate set.

If a pair has no successful model row, it is reported in the dry-run output under `unresolved_pairs` and no alias is proposed.

### Where the verdict lives

| Surface | Field | Notes |
|---------|-------|-------|
| **NEW** `batch_job_item.is_champion` | `Boolean`, default `False`, indexed | Flipped to `True` only for the chosen row per pair after the operator confirms the dry-run. Persisted so the heatmap can render champions distinctly. |
| **NEW** `batch_job.champion_summary` | `JSONB`, nullable | `{ "selected_at": iso8601, "selected_by": "operator"|"agent", "alias_namespace": "champion-batch-<id>-...", "count": N, "unresolved": [...] }`. One row per batch, written atomically alongside the alias inserts. |
| **EXISTING** `deployment_alias` (`app/features/registry/models.py`) | `alias_name` ↔ `run_id` | The mutation surface. Each champion lands here via `RegistryService.create_alias`, unchanged. |

> Alembic migration is forward-only (per `.claude/rules/security-patterns.md`); ships with both columns in one revision so the batch-runner MVP DB upgrade does not have to be re-rolled.

### Alias naming policy

**Recommended:** `champion-batch-{batch_id}-{store_id}-{product_id}` (lowercase, fits the existing pattern `^[a-z0-9][a-z0-9\-_]*$` from `app/features/registry/schemas.py:183`).

**Rationale:** the per-batch namespace removes the collision class entirely. The flat `champion-{store_code}-{sku}` form was rejected because:

- `store_code` / `sku` are external strings that can contain characters outside the alias pattern.
- Two operators running two batches over overlapping scopes would mutate each other's aliases — the registry alias is mutable (`create_alias` updates an existing row, `app/features/registry/service.py:460`), so the second batch would silently overwrite the first.
- A per-batch namespace makes the historical trace recoverable (`SELECT alias_name FROM deployment_alias WHERE alias_name LIKE 'champion-batch-7-%'`).

**Collision policy:** because the namespace embeds `batch_id` (unique per `batch_job`), the only collision class is a *re-run of `promote-champions` against the same batch*, which is the idempotency case below.

### Idempotency

Re-running `POST /batch/{id}/promote-champions` against the same batch:

- Recomputes the dry-run set deterministically (same metric data + same tie-break order → same winners).
- The apply call iterates the proposed set and calls `create_alias` for each row. `create_alias` already upserts (`app/features/registry/service.py:460-469`), so re-applying produces no churn: rows match the existing alias → run_id mapping and no new DB writes other than `updated_at` bumps.
- **Contract:** `dry_run.diff == []` when the batch has already been promoted and no new successful `batch_job_item` rows have been added since.

### HITL gate

Two execution paths:

1. **Operator via UI / HTTP** — `POST /batch/{id}/promote-champions?confirm=true` is the explicit confirm. The endpoint requires no agent-approval flow because the request itself is the human's confirmation. The route MUST first be called without `confirm=true` (or with `confirm=false`) to receive the dry-run preview; the UI binds the confirm button only after the dry-run is rendered.

2. **Agent tool** — **NEW** `app/features/batch/agent_tools.py::promote_champions` that wraps the same service method. The tool MUST be added to `agent_require_approval` in `app/core/config.py:168` (currently `["create_alias", "archive_run", "save_scenario"]`) alongside the existing mutation tools. The pattern is identical to `save_scenario` (`app/features/scenarios/agent_tools.py:13-149`) — the tool name in `agent_require_approval` is what makes the agent layer pause for `POST /agents/sessions/{id}/approve` before the mutation lands.

Both paths converge on `BatchChampionService.apply(batch_id, ...)`. There is one mutation function, two entry points, one gate.

### API surface (NEW)

```python
# app/features/batch/schemas.py  (NEW)

class ChampionCandidate(BaseModel):
    model_config = ConfigDict(strict=True)
    store_id: int = Field(strict=True)
    product_id: int = Field(strict=True)
    winner_run_id: str
    winner_model_type: Literal[
        "naive", "seasonal_naive", "moving_average", "regression", "lightgbm"
    ]
    wape: float
    smape: float
    proposed_alias_name: str
    existing_alias_run_id: str | None  # the alias's current target (None if new alias)

class PromoteChampionsDryRun(BaseModel):
    batch_id: int
    candidates: list[ChampionCandidate]
    unresolved_pairs: list[tuple[int, int]]
    diff_summary: dict[str, int]  # {"new": N, "updated": N, "unchanged": N}

class PromoteChampionsResult(BaseModel):
    batch_id: int
    applied: list[ChampionCandidate]
    skipped: list[ChampionCandidate]   # rows where the existing alias already pointed at the winner
    selected_at: datetime
```

```http
GET  /batch/{batch_id}/champions             # always dry-run preview (no mutation)
POST /batch/{batch_id}/promote-champions     # body: { confirm: bool } — confirm=false echoes the dry-run, confirm=true applies
```

Both routes return RFC 7807 problem+json on:

- batch not found → 404
- batch not in terminal state (`status != "completed"`) → 409
- batch has zero successful items → 422
- `confirm=true` against a batch with `champion_summary != null` whose computed-winners set equals the persisted set → 200 with `applied=[]` (idempotent no-op, not an error)

### Test plan (Champion Selection)

Per `.claude/rules/test-requirements.md`:

- **Unit (`app/features/batch/tests/test_champion_selection.py`):**
  - Tie-break: two model rows with identical WAPE → the lower-sMAPE one wins; with identical sMAPE → the earlier `created_at` one wins.
  - NaN WAPE row is excluded from the candidate set.
  - All-NaN pair lands in `unresolved_pairs`, not `candidates`.
  - Deterministic re-computation: same fixture → identical proposed set.
  - Empty batch → `PromoteChampionsDryRun` with empty `candidates` and the 422-trigger flag.

- **Integration (`app/features/batch/tests/test_routes.py`, marked `@pytest.mark.integration`):**
  - Happy path: seed a completed batch with three model types per pair → dry-run lists the expected winners → apply creates the aliases → `GET /registry/aliases/{name}` returns the winner `run_id`.
  - Idempotency: apply twice → second response has `applied=[]` (no churn) and `deployment_alias.updated_at` does not advance.
  - HITL gate: `promote_champions` agent tool name MUST be present in `settings.agent_require_approval` (mirror the assertion at `app/features/scenarios/tests/test_agent_tools.py:33`).
  - Alias-pattern compliance: every `proposed_alias_name` matches `^[a-z0-9][a-z0-9\-_]*$`.
  - SUCCESS-only invariant: a candidate whose `model_run.status != "success"` is excluded (registry refuses to alias it anyway — `app/features/registry/service.py:446-451`).

- **Pydantic v2 strict-mode policy:** request bodies that contain `datetime`/`date`/`UUID`/`Decimal` MUST mark those fields `Field(strict=False, ...)` per `docs/_base/SECURITY.md` § "Pydantic v2 strict mode on FastAPI request bodies". The `selected_at` round-trip MUST be exercised in a `Model.model_validate({...})` test (FastAPI's `validate_python` path).

---

## Item 2 — Portfolio Heatmaps

### Endpoint shape (NEW)

```http
GET /batch/{batch_id}/heatmap?metric=wape&model_type=lightgbm&include_champions=true
```

| Query param | Type | Default | Notes |
|-------------|------|---------|-------|
| `metric` | `Literal["wape","smape","mae","bias","convergence"]` | `"wape"` | `convergence` = % models that produced a non-NaN row for the pair |
| `model_type` | `Literal[...] \| None` | `None` | When set, restricts the surface to one model family; when `None`, the cell shows the *champion's* metric (so the grid is one cell per pair regardless of how many model types ran) |
| `include_champions` | `bool` | `false` | Adds `is_champion` to every cell — used by the UI to render a winner badge |

**Response (Pydantic v2, NEW `app/features/batch/schemas.py::HeatmapResponse`):**

```python
class HeatmapCell(BaseModel):
    store_id: int
    product_id: int
    value: float | None              # None → no data (rendered as a "missing" cell, not zero)
    model_type: str                  # echo of selected or champion model
    run_id: str | None
    is_champion: bool | None
    sample_size: int

class HeatmapAxis(BaseModel):
    store_ids: list[int]             # ordered for grid rendering
    product_ids: list[int]           # ordered

class HeatmapResponse(BaseModel):
    batch_id: int
    metric: str
    model_type: str | None
    cells: list[HeatmapCell]         # sparse — only pairs with rows
    axes: HeatmapAxis
    color_scale: dict[str, float]    # {"min": 0.0, "p50": 0.21, "p95": 0.58, "max": 1.2}
```

The response is **sparse** (one row per realized pair, not |stores|×|products| rows). The axes give the rendering side enough information to lay out empty cells. A 100×100 portfolio with 70% scope coverage is ~7,000 cells — well within a JSON payload but at the limit of what a single Recharts/SVG render handles smoothly (see "Risks").

### Visualization — choice of rendering strategy

**Recharts has no native Heatmap component.** Verified by inspecting `frontend/src/components/charts/` — the five existing chart components (`time-series-chart.tsx`, `multi-series-chart.tsx`, `backtest-folds-chart.tsx`, `revenue-bar-chart.tsx`, `kpi-card.tsx`) all wrap Recharts primitives (`LineChart`, `BarChart`), and none implements a `store × product` matrix. Recharts' closest primitives are `ScatterChart` (with custom shapes) and `Treemap` — neither is the right semantics for "metric quality across a fixed two-axis grid."

> **Recommendation: TanStack Table with conditionally colored cells.**
>
> The existing `frontend/src/components/ui/table.tsx` (`TableCell`) is a shadcn primitive that already supports `className` for per-cell styling. TanStack Table is already a dependency (per the source feature doc and `INITIAL-MLZOO-D`). Combined, this yields:
>
> - Free row/column virtualization (`@tanstack/react-virtual`, an existing transitive dependency through TanStack Table) — solves the 100×100 perf risk.
> - Sortable axes by row/column aggregate (mean WAPE per store, mean WAPE per product).
> - Tooltip on cell hover via the existing shadcn `Tooltip` primitive (`frontend/src/components/ui/tooltip.tsx`).
> - Click handler → routes to the per-`(store, product)` batch result detail without a new chart abstraction.
>
> The alternative — a hand-rolled SVG grid — was rejected because (a) it duplicates virtualization logic Recharts/TanStack solved, and (b) `.claude/rules/shadcn-ui.md` forbids hand-rolling UI when a primitive applies.

**Color scale:**

- Sequential palette (single-hue) for WAPE / sMAPE / MAE / convergence — quality metric where lower is better, one direction of meaning.
- Diverging palette for bias only — bias is positive *or* negative around zero.
- Colorblind-safe palette (Viridis or Cividis — both shipped as utility constants, not new dependencies). Final palette pick is **Open Question Q3**.
- Legend rendered above the grid using the existing `Card` + `Badge` shadcn primitives.

### Drilldown

Clicking a cell navigates to `/explorer/batch/{batch_id}/item/{store_id}/{product_id}` (route added by the MVP batch runner INITIAL — verify it exists when the PRP author lands this work, **mark NEW if not**). Falls back to `/explorer/run-detail/{cell.run_id}` if the per-item detail page isn't yet built.

### Frontend touchpoints

- **NEW** `frontend/src/pages/visualize/heatmap.tsx` — new page slot under the existing `visualize/` folder, alongside `backtest.tsx`, `forecast.tsx`, `demand.tsx`, `planner.tsx`. Mirrors the metric-selector pattern from `frontend/src/pages/visualize/backtest.tsx:55-60` (the `MODEL_OPTIONS` block).
- **NEW** `frontend/src/components/charts/portfolio-heatmap.tsx` — the TanStack-Table-with-colored-cells primitive. Exported via `frontend/src/components/charts/index.ts` alongside the existing five chart components.
- **NEW** `frontend/src/hooks/use-batch-heatmap.ts` — TanStack Query wrapper over `GET /batch/{id}/heatmap`. Mirrors `frontend/src/hooks/use-jobs.ts` style.
- **NEW** `frontend/src/components/batch/champion-promotion-panel.tsx` — the action UI for Item 1. Renders the dry-run candidate list (uses shadcn `Table`), then a confirm `AlertDialog` (`frontend/src/components/ui/alert-dialog.tsx`) before posting `?confirm=true`.
- **EXTEND** the batch-detail page (NEW — owned by the MVP runner INITIAL): add two new tab panels — "Heatmap" (mounts the new visualize/heatmap render in-place) and "Promote Champions" (mounts the promotion panel).
- **UI design gate:** any change under `frontend/src/` MUST go through the workflow in `.claude/rules/ui-design.md` (Stitch → frontend-design → webapp-testing browser verification) and the component-layer rules in `.claude/rules/shadcn-ui.md`.

### Test plan (Heatmap)

- **Unit (`app/features/batch/tests/test_heatmap.py`):**
  - Empty batch → empty `cells`, axes populated only by scope.
  - All-NaN metric for a pair → cell `value` is `None`, not `0.0` (the rendering distinction depends on this).
  - `model_type=None` returns one cell per pair using the champion's row.
  - `metric=convergence` returns a value in `[0.0, 1.0]` per pair.
  - Color-scale percentiles are computed over the non-`None` cells only.

- **Frontend snapshot/render (`frontend/src/components/charts/portfolio-heatmap.test.tsx`):**
  - 3×3 grid renders with one missing-cell placeholder.
  - Cell click invokes the supplied handler with the right `(store_id, product_id)`.
  - Legend bin count matches the color-scale percentiles in the payload.
  - Per `.claude/rules/test-requirements.md`: non-trivial frontend state → vitest test required.

- **Frontend browser verification:** per `.claude/rules/ui-design.md`, type-check + tests passing ≠ UI works. The PRP author MUST exercise the heatmap page in a real browser via `webapp-testing` (or the `agent-browser` skill) before the PR is marked ready.

---

## Shared Aggregation Service

A single service method backs both endpoints — both items consume the same `batch_job_item × model_run × metrics` join, and there is no second reader.

```python
# app/features/batch/service.py  (NEW)

class BatchAnalyticsService:
    async def aggregate_by_series(
        self,
        db: AsyncSession,
        batch_id: int,
        *,
        model_type: str | None = None,
    ) -> list[SeriesAggregate]:
        """One row per (store_id, product_id, model_type) for the batch.

        Returns the metric tuple (wape, smape, mae, bias, sample_size, is_champion)
        from the JSONB column on batch_job_item (NEW), joined to the underlying
        model_run for the run_id and status. Filters to status='success' rows.

        Used by:
        - BatchChampionService.compute_winners (Item 1, dry-run + apply)
        - HeatmapService.build (Item 2, cell layout + champion marker)
        """
        ...
```

- **Why not two services?** The data fetched is identical; the only difference is the post-processing — Item 1 reduces to one row per `(store, product)` (the winner), Item 2 lays out all rows. Splitting the query duplicates the JSONB extraction and the JOIN to `model_run`.
- **No cross-slice imports.** `BatchAnalyticsService` reads `batch_job_item` + `model_run` via the `app/shared/` (or `app/features/data_platform/`) ORM layer; it does NOT import `RegistryService`. The champion-apply step calls `RegistryService.create_alias` at the route layer, not the service layer — mirrors the pattern at `app/features/scenarios/service.py` per `docs/_base/ARCHITECTURE.md` § "Cross-slice read-only import pattern".

---

## Data Model Delta

| Table | Column | Type | NEW or EXTEND | Notes |
|-------|--------|------|---------------|-------|
| `batch_job_item` | `metrics` | `JSONB nullable` | **EXTEND** (added by MVP) | MUST contain `{ "wape": float, "smape": float, "mae": float, "bias": float, "sample_size": int }`. If the MVP ships without `bias`/`sample_size`, the PRP must call that out. |
| `batch_job_item` | `is_champion` | `Boolean default False, indexed` | **NEW (this PRP)** | Default False; flipped to True for the per-pair winner only after the operator confirms the dry-run. |
| `batch_job` | `champion_summary` | `JSONB nullable` | **NEW (this PRP)** | Single-write audit: `{selected_at, selected_by, alias_namespace, count, unresolved}`. |
| `deployment_alias` | — | — | **EXTEND** (no schema change) | `RegistryService.create_alias` inserts per-pair rows; alias-name pattern unchanged. |

**Migration discipline:** one Alembic revision adds `batch_job_item.is_champion` and `batch_job.champion_summary` together. Migrations are forward-only after merge (`.claude/rules/security-patterns.md`). The migration MUST be reversible-on-empty-DB so the CI `migration-check` job stays green (`docs/_base/PIPELINE_CONTRACT.md`).

---

## Security Delta

Per `.claude/rules/security-patterns.md` § "LLM / Agent layer":

- **NEW** agent tool `promote_champions` (`app/features/batch/agent_tools.py`). Tool name MUST be appended to `agent_require_approval` in `app/core/config.py:168`:

  ```python
  # Current:   ["create_alias", "archive_run", "save_scenario"]
  # New:       ["create_alias", "archive_run", "save_scenario", "promote_champions"]
  ```

- The configuration system already surfaces `agent_require_approval` via `GET /config/ai` (`app/features/config/service.py:151`); the new entry will appear automatically.
- Test enforcement: a presence assertion mirrors `app/features/scenarios/tests/test_agent_tools.py:33-34` — `assert "promote_champions" in get_settings().agent_require_approval`.
- **Input validation:** the tool's argument model is Pydantic v2 with `ConfigDict(strict=True)`. `batch_id` is a JSON-native int (no strict-mode policy override needed). Any `datetime` field MUST carry `Field(strict=False, ...)` per `docs/_base/SECURITY.md`.
- **Logging:** the registry already emits `registry.alias_created` / `registry.alias_updated` (`app/features/registry/service.py:465-481`). The new service adds `batch.champions_promoted` (batch_id, count, source=`operator|agent`). No prompts or responses logged — only structured event names and counts, per the rule.
- **No new external dependencies.** No HTTPS clients, no `verify=False` exposure, no `subprocess`, no `eval`/`exec`. The change is closed over the existing DB + agent surfaces.

---

## API Delta (summary)

```http
# Champion Selection
GET    /batch/{batch_id}/champions                          → PromoteChampionsDryRun
POST   /batch/{batch_id}/promote-champions                  → PromoteChampionsResult  (body: {confirm: bool})

# Heatmap
GET    /batch/{batch_id}/heatmap?metric=wape&model_type=…   → HeatmapResponse
```

All four error paths return `application/problem+json` via `app/core/problem_details.py`:

| Status | Trigger |
|--------|---------|
| 404 | Batch ID does not exist |
| 409 | Batch is still running / pending |
| 422 | Batch has zero successful items, or `metric` not in allow-list |
| 200 (idempotent no-op) | `promote-champions` re-run against an already-promoted batch — `applied=[]` |

Routes register in `app/main.py` (the existing wiring pattern, line 136-147). The new slice `app/features/batch/` follows the standard `{models, schemas, service, routes, tests}.py` layout per `docs/_base/ARCHITECTURE.md` § "Vertical slices."

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Alias-namespace collision** between batches that re-run a scope | Low | Med | Per-batch namespace (`champion-batch-{batch_id}-…`) eliminates the class; the registry upsert handles within-batch re-runs |
| **Champion churn** when WAPE differs by ε between runs | Med | Low | Tie-break chain (WAPE → sMAPE → earliest `created_at`) makes the verdict deterministic for a fixed metric snapshot. The MVP's metrics are computed once at backtest time and stored on `batch_job_item.metrics` — they don't drift mid-batch. |
| **100×100 portfolio renders slowly** | Med | Med | TanStack Table virtualization (free with the table primitive). PRP author MUST run the browser-perf check from `.claude/rules/ui-design.md` before merge. |
| **Recharts has no Heatmap component** | Confirmed | — | Use TanStack Table + shadcn `TableCell` (see "Visualization — choice of rendering strategy"). |
| **MVP's `batch_job_item.metrics` JSONB is missing `bias` / `sample_size`** | Med | High | Block this PRP behind the MVP INITIAL writing both fields. The "depends_on" front-matter is the gate. |
| **Operator promotes champions, then re-runs the batch** | Med | Low | Re-running `promote-champions` is idempotent (the apply path upserts via `create_alias` and short-circuits identical mappings). The new aliases overwrite the prior ones in-place, which is the correct semantics — the batch ID is the same. |
| **An agent calls `promote_champions` without HITL** | Catastrophic | — | Presence assertion in the test suite + the rule that no agent tool mutating state can land without the `agent_require_approval` entry. Audited at PR time per `.claude/rules/security-patterns.md`. |
| **`batch_job_item.is_champion` rewritten by a parallel batch** | Low | Low | The column lives on `batch_job_item`, which is scoped to a single `batch_id`. No two batches write the same row. |
| **Heatmap legend confuses operators on bias (diverging) vs WAPE (sequential)** | Low | Low | The selector forces a metric pick before the grid renders; the legend palette swaps deterministically per metric. Tooltip on each cell echoes the raw value. |

---

## Open Questions

- [ ] **Q1: Alias namespace format final form.** The recommendation is `champion-batch-{batch_id}-{store_id}-{product_id}`. The PRP author MUST decide whether to use opaque numeric IDs (recommended for collision-safety, cited above) or human-readable `{store_code}-{sku}` slugs (better operator UX, but the registry alias pattern `^[a-z0-9][a-z0-9\-_]*$` would need a slugifier).
- [ ] **Q2: Should `GET /batch/{id}/champions` cache the dry-run, or recompute on every call?** Recompute is simpler and the cost is bounded by portfolio size; cache would make the UX snappier but introduces invalidation logic. Default to recompute; revisit if a 1k-pair batch trips the user.
- [ ] **Q3: Final colorblind-safe palette choice.** Viridis vs Cividis vs OkLab-based scale. Pick one and ship it as a single utility constant — `frontend/src/lib/heatmap-palette.ts` (NEW).
- [ ] **Q4: Virtualization threshold.** Below what cell count is `@tanstack/react-virtual` overhead unjustified? Empirically pick (likely ≥ 500 cells); below that, render without virtualization.
- [ ] **Q5: Multi-batch heatmap comparison** — explicitly deferred. The PRP author MUST NOT widen scope; capture it as a follow-up `INITIAL-*` if requested.
- [ ] **Q6: Does the per-`(store, product)` batch-item detail page exist by the time this lands?** It's owned by the MVP runner INITIAL. If not, the heatmap drilldown target falls back to `/explorer/run-detail/{run_id}` — call this out in the PRP and don't block.
- [ ] **Q7: Agent prompt copy** — the experiment agent's system prompt (`app/features/agents/agents/base.py:285`) currently lists `tool_create_alias` / `tool_archive_run` / `tool_save_scenario`. Append `tool_promote_champions` with one sentence of guidance: "Use to promote per-series winners after a batch completes (requires approval)."

---

## Cross-Reference

- **Source feature doc:** `docs/optional-features/06-portfolio-forecasting-batch-runner.md` § Full Version items 4 + 5.
- **Architecture invariants:** `docs/_base/ARCHITECTURE.md` § Vertical slices, § Cross-slice read-only import pattern.
- **API contract conventions:** `docs/_base/API_CONTRACTS.md` § HTTP Endpoints (registry alias rows, registry status-machine).
- **Domain model:** `docs/_base/DOMAIN_MODEL.md` § Core Aggregates → `model_run`, "alias may point only to a `success` run."
- **Security gates:** `docs/_base/SECURITY.md` § LLM / Agent Security; `.claude/rules/security-patterns.md` § LLM / Agent layer.
- **Test policy:** `.claude/rules/test-requirements.md` § "When new tests are required."
- **UI gates:** `.claude/rules/ui-design.md`; `.claude/rules/shadcn-ui.md`.
- **Output conventions:** `.claude/rules/output-formatting.md` (CLI / report outputs only — not relevant to the API surface).
- **Existing precedents to mirror:**
  - `app/features/scenarios/agent_tools.py:140` — `save_scenario` is the closest existing pattern for an approval-gated, batch-aware mutation agent tool.
  - `app/features/registry/service.py:421-495` — `create_alias` mutation surface; consumed unchanged.
  - `app/features/scenarios/tests/test_agent_tools.py:33` — the `agent_require_approval` presence assertion to mirror.
  - `frontend/src/pages/visualize/backtest.tsx:55-60` — the metric/model selector pattern for the new heatmap page.
  - `PRPs/INITIAL/INITIAL-14.md` — INITIAL doc format and tone to mirror.

---

## References (paths verified)

| Path | Status |
|------|--------|
| `app/features/registry/models.py` | Exists |
| `app/features/registry/service.py` (`create_alias` at line 421) | Exists |
| `app/features/registry/schemas.py` (alias-name pattern at line 183) | Exists |
| `app/features/backtesting/metrics.py` (WAPE/sMAPE/MAE definitions) | Exists |
| `app/features/scenarios/agent_tools.py` (`save_scenario` HITL precedent) | Exists |
| `app/features/scenarios/tests/test_agent_tools.py:33` (approval-list assertion) | Exists |
| `app/core/config.py:168` (`agent_require_approval` default list) | Exists |
| `app/features/agents/agents/base.py:255-265` (`requires_approval` helper) | Exists |
| `app/main.py:15-32` (router import + wiring pattern) | Exists |
| `frontend/src/components/charts/index.ts` (existing chart barrel — 5 components) | Exists |
| `frontend/src/components/ui/table.tsx` (shadcn `TableCell`) | Exists |
| `frontend/src/components/ui/alert-dialog.tsx` | Exists |
| `frontend/src/components/ui/tooltip.tsx` | Exists |
| `frontend/src/pages/visualize/backtest.tsx` (page slot pattern) | Exists |
| `app/features/batch/` | **NEW** — created by the MVP runner INITIAL (not yet built) |
| `batch_job` / `batch_job_item` tables | **NEW** — created by the MVP runner INITIAL (not yet built) |
| `batch_job_item.is_champion` + `batch_job.champion_summary` | **NEW** (this PRP) |
| `app/features/batch/agent_tools.py::promote_champions` | **NEW** (this PRP) |
| `frontend/src/pages/visualize/heatmap.tsx` | **NEW** (this PRP) |
| `frontend/src/components/charts/portfolio-heatmap.tsx` | **NEW** (this PRP) |
| `frontend/src/components/batch/champion-promotion-panel.tsx` | **NEW** (this PRP) |
| `frontend/src/hooks/use-batch-heatmap.ts` | **NEW** (this PRP) |
| `frontend/src/lib/heatmap-palette.ts` | **NEW** (this PRP) |
| Recharts native `Heatmap` component | **Does NOT exist** (verified by grep over `frontend/`) — drives the TanStack-Table rendering choice |
