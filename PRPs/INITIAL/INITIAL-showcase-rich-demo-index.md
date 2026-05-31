# INITIAL-showcase-rich-demo-index.md — `/showcase` Rich Demo Control Center Roadmap

> **Status:** Planning. Index for the four-PRP `/showcase` upgrade epic.
> **Umbrella INITIAL:** `PRPs/INITIAL/INITIAL-showcase-rich-demo-control-center.md`
> **Walkthrough draft:** `docs/user-guide/showcase-walkthrough.md`

## FEATURE:

This epic turns `/showcase` from a flat 11-step baseline-only demo into a
phase-grouped, full-lifecycle operator demo control center that exercises the
whole ForecastLabAI stack in one live, browser-streamed run: data → V1+V2
modeling → feature-aware backtesting with horizon buckets → registry decisions
(champion/challenger + stale aliases + safer Promote) → portfolio batch →
scenario simulate/save/compare → curated RAG indexing → agent HITL → ops
snapshot. The four-PRP slicing (PRP-38..41) balances a shippable MVP
foundation (PRP-38, phase accordion + scenario picker + ONE V2 run) with the
full Option-B roadmap (PRP-39 registry decisions + portfolio batch, PRP-40
planning + knowledge, PRP-41 agent + ops + final polish).

Recommended PRP sequence:

| Order | INITIAL | Scope | Lifecycle area unlocked |
| --- | --- | --- | --- |
| 1 | `PRPs/INITIAL/INITIAL-showcase-38-data-modeling-lifecycle.md` | Phase accordion + scenario picker + `showcase-rich` preset + phase-2 enrichment + historical backfill + V1 baselines + ONE V2 prophet_like run + bucket-visible feature-aware backtest + per-step Inspect links | Data, ingest, features, V1+V2 modeling, backtesting buckets |
| 2 | `PRPs/INITIAL/INITIAL-showcase-39-decision-portfolio-lifecycle.md` | Champion-compat compare (V1 vs V2) + stale-alias trigger (feature_frame_version_mismatch) + safer-Promote flow + small portfolio batch (quick_baseline_sweep preset, 3×2×3 matrix) | Registry decisions, alias staleness, safer Promote, portfolio batch |
| 3 | `PRPs/INITIAL/INITIAL-showcase-40-planning-knowledge-lifecycle.md` | Scenario simulate + save plan + multi-plan compare + embedding-provider probe + curated RAG indexing of docs/user-guide/ + retrieve probe | Scenarios, RAG knowledge |
| 4 | `PRPs/INITIAL/INITIAL-showcase-41-agent-ops-polish.md` | Agent HITL flow (save_scenario approval) + ops snapshot + KPI strip + Inspect-Artifacts post-run panel + localStorage run history + Stop button + walkthrough docs polish | Agents (HITL), Ops, cross-cutting UI polish |

Dependency graph:

```text
PRP-38 Foundation (data + V1/V2 modeling + phase accordion)
   |
   |---> PRP-39 Decision + Portfolio (registry decisions + batch)
   |
   |---> PRP-40 Planning + Knowledge (scenarios + RAG)
              |
              v
              PRP-41 Agent HITL + Ops + Final Polish
              (requires PRP-39 stale-alias chip + PRP-40 RAG corpus for the
               KPI strip and Inspect-Artifacts panel deep links)
```

Dependency rules:

- PRP-38 — no prerequisites (foundation).
- PRP-39 — depends on PRP-38 (consumes the V2 run on the showcase grain).
- PRP-40 — depends on PRP-38 (consumes the registered champion run). Can be
  generated and merged in parallel with PRP-39.
- PRP-41 — depends on PRP-39 AND PRP-40 (KPI strip counts saved scenarios +
  RAG chunks + batch items; Inspect-Artifacts panel deep-links into the
  stale-alias chip + saved scenarios + indexed corpus).

Parallelism:

- PRP-39 and PRP-40 are independent siblings; they may be authored and
  implemented in parallel after PRP-38 lands.
- PRP-41 is strictly after PRP-39 and PRP-40 both merge.

## EXAMPLES:

Read these in the order listed before generating PRPs from this roadmap:

- `PRPs/INITIAL/INITIAL-showcase-rich-demo-control-center.md` — umbrella
  INITIAL of this epic (entry point — read before any sliced INITIAL).
- `PRPs/INITIAL/INITIAL-showcase-38-data-modeling-lifecycle.md` — PRP-38
  (foundation: phase accordion, scenario picker, `showcase-rich` preset,
  data enrichment + historical backfill, V1 baselines + ONE V2 prophet_like
  run, bucket-visible backtest, per-step Inspect links).
- `PRPs/INITIAL/INITIAL-showcase-39-decision-portfolio-lifecycle.md` — PRP-39
  (champion-compat compare, stale-alias trigger, safer-Promote flow,
  `quick_baseline_sweep` 3×2×3 batch).
- `PRPs/INITIAL/INITIAL-showcase-40-planning-knowledge-lifecycle.md` — PRP-40
  (scenario simulate + save + multi-plan compare, embedding-provider probe,
  curated `docs/user-guide/` RAG indexing + retrieve probe).
- `PRPs/INITIAL/INITIAL-showcase-41-agent-ops-polish.md` — PRP-41 (agent HITL
  flow with `save_scenario` approval, ops snapshot, KPI strip, Inspect
  Artifacts post-run panel, localStorage last-5-runs strip, Stop button,
  walkthrough doc polish).
- `docs/user-guide/showcase-walkthrough.md` — planned-features walkthrough
  draft; PRP-41 ships the polished version.
- `PRPs/INITIAL/INITIAL-forecast-intelligence-index.md` — sibling
  epic-index doc; this file mirrors its layout (sequence table, dependency
  graph, parallelism note, recommended execution).
- `PRPs/PRP-37-forecast-intelligence-C-interactive-ui.md` — pattern for the
  Task-1 contract-probe gate each sliced PRP adopts.
- `PRPs/ai_docs/prp-37-contract-probe-report.md` — pattern for each
  per-slice contract-probe report (`PRPs/ai_docs/prp-{N}-contract-probe-report.md`).

## DOCUMENTATION:

Internal — load when authoring any of the sliced PRPs:

- `AGENTS.md` — universal agent brief; vertical-slice rule, validation gates,
  RFC 7807 envelope, hard-rules list.
- `CLAUDE.md` — Claude-specific operating index and deep-dive doc map.
- `docs/_base/API_CONTRACTS.md` — every endpoint each PRP drives (`/demo/*`,
  `/seeder/*`, `/forecasting/*`, `/backtesting/*`, `/registry/*`, `/batch/*`,
  `/scenarios/*`, `/rag/*`, `/agents/*`, `/ops/*`, `/config/providers/health`).
- `docs/_base/RUNBOOKS.md` — Showcase failure-mode catalogue ("Showcase page
  (`/showcase`) pipeline fails at step X"); each PRP extends this list
  additively for the new steps it ships.
- `docs/_base/DOMAIN_MODEL.md` — Comparable-run rule + stale-alias V mismatch
  enum (load-bearing for PRP-39).
- `docs/_base/SECURITY.md` — `agent_require_approval` + HITL gate (PRP-41
  must not widen the agent mutation surface without updating the list).
- `docs/_base/PIPELINE_CONTRACT.md` — CI gates each PRP must pass (the four
  required status checks on `dev` + `main`).
- `.claude/rules/product-vision.md` — single-host, no managed cloud,
  vertical-slice; every PRP must pass the litmus test.
- `.claude/rules/test-requirements.md` — new step ⇒ new test (per-step
  pipeline test + route test for any new endpoint).
- `.claude/rules/shadcn-ui.md` — UI primitives must go through `shadcn` skill
  + MCP; no hand-rolled primitives.
- `.claude/rules/versioning.md` — pre-1.0 `feat:` → PATCH; the four PRPs
  produce four sequential PATCH releases.

External — reference during PRP execution (load via `mcp__claude_ai_contex7__`):

- shadcn/ui Accordion + Select — phase accordion + scenario picker (PRP-38).
- TanStack Query mutations + polling — every PRP's frontend wiring.
- FastAPI WebSocket — additive `StepEvent` schema (every PRP).
- PydanticAI tool-call lifecycle — HITL approval flow (PRP-41).

## OTHER CONSIDERATIONS:

### Global constraints (apply to every PRP in the epic)

- **No new tables.** Persistent state goes to localStorage in the browser
  (last-5-runs strip in PRP-41).
- **Vertical-slice rule.** `app/features/demo/` MUST NOT import from any other
  `app/features/*` slice; every cross-slice call uses `httpx.ASGITransport`.
  Helpers CLI scripts provide today land as new endpoints on the owning slice
  (e.g., `POST /seeder/phase2-enrichment` in `app/features/seeder/`).
- **WebSocket `StepEvent` contract is additive only.** New Optional fields
  (`phase_name`, `phase_index`, `phase_total`, `substep_*`); existing fields
  unchanged. No version key bump — clients ignore unknown additive fields.
- **Phase table is a stability invariant.** Backend `_phase_table()` and
  frontend `PHASE_DEFS` ship in the SAME PRP slice in lockstep;
  `test_phase_table_stable` (backend) + `phase-defs.test.ts` (frontend)
  enforce the match.
- **Skip gracefully on missing providers.** Every step that depends on an
  external provider (LLM key for `/agents/*`, embedding key for `/rag/*`)
  MUST use the `_llm_key_present()` gating pattern
  (`app/features/demo/pipeline.py:203`) and emit `skip` with a clear `detail`.
  A missing key is NEVER a `fail`.
- **No DB reset implied by the epic.** The existing opt-in "Reset database"
  checkbox stays; no PRP forces a reset on every run.
- **Pre-execution contract probe (mandatory per PRP).** Each PRP's Task 1
  mirrors `PRPs/ai_docs/prp-37-contract-probe-report.md` — verify every
  cited backend field/endpoint exists on `dev` before authoring the PRP body;
  output to `PRPs/ai_docs/prp-{N}-contract-probe-report.md`.
- **Frontend type-check command is project-scoped.** Each PRP MUST re-run
  `pnpm tsc --noEmit -p tsconfig.app.json` (NOT bare `tsc` — the thin root
  `tsconfig.json` has `"files": []` and will pass while the app tsconfig
  still has errors).
- **All five validation gates required.** ruff + ruff format + mypy +
  pyright + pytest (unit + integration) + migration-check —
  see `docs/_base/PIPELINE_CONTRACT.md`.

### Performance budgets (epic-wide)

- `demo_minimal`: ≤ 90 s wall-clock (backwards compat — no regression).
- `showcase-rich`: ≤ 240 s wall-clock (new budget; per-step timeout 120 s).

### Recommended execution sequence (the exact `/base_prp:prp-create` commands)

Run these in this exact order. Each command produces a PRP under `PRPs/`;
implement and merge each one before generating the next dependent slice.

```
1. /base_prp:prp-create PRPs/INITIAL/INITIAL-showcase-38-data-modeling-lifecycle.md
2. /base_prp:prp-create PRPs/INITIAL/INITIAL-showcase-39-decision-portfolio-lifecycle.md
3. /base_prp:prp-create PRPs/INITIAL/INITIAL-showcase-40-planning-knowledge-lifecycle.md
4. /base_prp:prp-create PRPs/INITIAL/INITIAL-showcase-41-agent-ops-polish.md
```

PRP-39 and PRP-40 may be generated in parallel after PRP-38 lands (both
depend ONLY on PRP-38). PRP-41 is strictly after PRP-39 AND PRP-40 both
merge.

### Suggested future issue titles

- `feat(api,ui): showcase pipeline — richer data + V1/V2 modeling foundation` (PRP-38)
- `feat(api,ui): showcase pipeline — decision + portfolio lifecycle` (PRP-39)
- `feat(api,ui): showcase pipeline — planning + knowledge lifecycle` (PRP-40)
- `feat(api,ui): showcase pipeline — agent + ops + final polish` (PRP-41)
