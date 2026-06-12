name: "PRP — Showcase Workspace E2: Full Preset Exposure (issue #391)"
description: |

## Purpose

Implement the first Parallel epic of the showcase-workspace initiative (umbrella #389):
surface all 8 `ScenarioPreset` values as guided, business-friendly cards in the
frontend `ScenarioPicker`, give per-preset demo seed profiles to the pipeline's
seed step, and attach expected-skip semantics (card caveat + runbook entry) to
presets that cannot complete every pipeline step. Frontend-mostly; the backend
already accepts the full enum.

## Core Principles

1. **Context is King**: every reference below was verified against the live code on 2026-06-12 (branch dev @ 0493192, post-E1 merge).
2. **Validation Loops**: each level is executable as written.
3. **Information Dense**: patterns cite exact file:line.
4. **Progressive Success**: backend seed profiles → types → picker cards → lockstep tests → docs → browser dogfood.
5. **Global rules**: follow CLAUDE.md / AGENTS.md; all five backend CI gates must pass; UI work follows `.claude/rules/ui-design.md` + `.claude/rules/shadcn-ui.md`.

---

## Goal

A user on `/showcase` can pick any of the 8 seeder presets (`retail_standard`,
`holiday_rush`, `high_variance`, `stockout_heavy`, `new_launches`, `sparse`,
`demo_minimal`, `showcase_rich`) from a card grid that explains, per preset:
what data it seeds (stores × products × window), its business character (promos,
stockouts, launches, noise), an estimated wall-clock, and — where applicable —
an **expected-skip/fail caveat** so a non-green outcome reads as documented
behavior, not a bug. Re-seeding with any preset produces a pipeline run that
either goes green or fails/skips exactly as its card predicts.

**Deliverable** (all additive):

- `app/features/demo/pipeline.py` — `_SCENARIO_SEED_PROFILE` extended from 3 to all 8 presets via a `_SeedProfile` NamedTuple that supports an optional calendar-pinned window (needed by `holiday_rush`); `step_seed` honors the pinned window.
- `frontend/src/types/api.ts` — `ScenarioPreset` union widened from 3 to all 8 string values.
- `frontend/src/components/demo/ScenarioPicker.tsx` — shadcn `<Select>` replaced by an 8-card grid (existing `value`/`onChange`/`disabled` props preserved so `showcase.tsx` wiring does not change shape).
- Tests: backend pipeline unit tests (profiles exhaustive, pinned window posted, phase-table shape for the 5 new presets), frontend `ScenarioPicker.test.tsx` rewrite + `PHASE_DEFS.test.ts` additions.
- Docs: `docs/_base/API_CONTRACTS.md` scenario-union correction; `docs/_base/RUNBOOKS.md` showcase entry #28 (per-preset expected-outcome matrix, sparse NaN-WAPE trap).

**Success definition**: all Success Criteria check off, the five backend gates +
frontend lint/test are green, and a real-browser dogfood shows all 8 cards,
runs `retail_standard` (re-seeded) to a green 11-step pipeline, and shows the
documented caveat on the `sparse` card.

## Why

- Umbrella #389: the UI exposes only 3 of 8 presets even though `DemoRunRequest.scenario` is typed as the full enum (`app/features/demo/schemas.py:59-63`) and `/seeder/generate` validates any of the 8 names (`app/features/seeder/service.py:59-71`).
- Without per-preset seed profiles, the 5 unmapped presets silently fall back to the demo_minimal profile (3×10×92d) (`app/features/demo/pipeline.py:479-485` + `.get` default at `:492-495`) — cards could not be truthful about what a re-seed generates.
- `sparse` already ships in the picker with NO caveat; its 50% missing grains + random gaps can produce a NaN-WAPE backtest **fail** (`pipeline.py:763-765`) that looks like a bug. E2 makes that an expected, documented outcome.
- E2 is Parallel after Foundation (E1 #390, merged as PR #394); it does not touch the workspace table and can land independently of E3 (#392) / E4 (#393).

## What

### User-visible behavior

- The Scenario control on `/showcase` becomes a card grid with all 8 presets. Each card shows: a business-friendly title, the monospace preset id, a one-line data/character description, an estimated wall-clock, and (where applicable) a caveat badge — `sparse` gets an "expected fail/skip" badge, `holiday_rush` a "pinned 2024 window" badge.
- Selection behavior, default (`demo_minimal`), the Run/Stop buttons, Re-seed/Reset checkboxes, and the WS start frame are unchanged in shape — only the picker widget and the set of accepted values change.
- A hint line under the grid: switching presets only changes the data when **Re-seed first** is ticked (otherwise the run reuses the currently seeded dataset).
- Re-seeding with any of the 5 newly exposed presets seeds a demo-scaled dataset (5×15×180d profile; `new_launches` 5×25×180d; `holiday_rush` the calendar-pinned Oct–Dec 2024 window) that carries the preset's character (noise, promos, stockouts, launch ramps, gaps) from `SeederConfig.from_scenario`.

### Technical requirements

- All 5 newly exposed presets run the legacy 11-step phase table — `_phase_table` branches only on `SHOWCASE_RICH` (`pipeline.py:2510-2533`) and `phaseDefsForScenario` mirrors that (`frontend/src/components/demo/PHASE_DEFS.ts:113-119`). NO phase-table change in E2.
- The pipeline's seed request keeps overriding preset dims/window by design — `/seeder/generate` applies explicit `stores`/`products`/`start_date`/`end_date` over the preset and preserves the preset's behavioral configs (`app/features/seeder/service.py:213-226`; `sparsity` is preserved because the pipeline sends `0.0` and the override fires only `if params.sparsity > 0` at `:225-226`).
- Every demo seed window stays ≥ 75 days so a follow-up `showcase_rich` run with `skip_seed=true` clears the `historical_backfill` gate (`pipeline.py:829-833`; gate = `3*(14+1)+30 = 75`).
- No pipeline behavior change for sparse: a NaN-WAPE backtest still FAILS (`pipeline.py:763-765`); E2 ships labeling + docs, not a graceful-skip rework (that would mask real regressions on healthy presets).
- `ScenarioPicker` keeps its exact props interface (`value: ScenarioPreset`, `onChange`, `disabled?` — `ScenarioPicker.tsx:39-43`) so `showcase.tsx:187` is untouched.

### Success Criteria

- [ ] `frontend/src/types/api.ts` `ScenarioPreset` lists all 8 values; `pnpm lint && pnpm test --run` green; no NEW `tsc -b` errors in touched files.
- [ ] The picker renders 8 cards; clicking one fires `onChange` with the preset value; the selected card is visually + aria-marked; all cards disable while a run is in flight.
- [ ] `sparse` card carries an expected-fail/skip caveat; `holiday_rush` card carries the pinned-window caveat.
- [ ] `_SCENARIO_SEED_PROFILE` covers ALL 8 enum members (exhaustiveness test) and `step_seed` posts: `holiday_rush` → `start_date=2024-10-01`, `end_date=2024-12-31`; `retail_standard` → 5 stores, 15 products, 180-day today-anchored window.
- [ ] `_phase_table(p)` for each of the 5 new presets equals the DEMO_MINIMAL shape (backend parametrized test) and `phaseDefsForScenario(p)` matches (frontend lockstep test).
- [ ] `docs/_base/API_CONTRACTS.md` documents the full 8-value union on POST /demo/run + the WS start frame; `docs/_base/RUNBOOKS.md` gains showcase entry #28 (preset expected-outcome matrix).
- [ ] Backend gates green: `uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pyright app/ && uv run pytest -v -m "not integration"`.
- [ ] Real-browser dogfood (Level 4): 8 cards visible; `retail_standard` re-seed run goes green (11 steps); legacy behavior unchanged (`demo_minimal` default).

## All Needed Context

### Documentation & References

```yaml
# MUST READ — codebase patterns (all verified 2026-06-12, dev @ 0493192)

- file: app/shared/seeder/config.py
  why: |
    ScenarioPreset enum at lines 37-47 (8 members, string values are the wire
    values). Window constants at 10-25 (DEMO_MINIMAL_SPAN_DAYS=91,
    SHOWCASE_RICH_SPAN_DAYS=180). from_scenario at 527-695 defines each
    preset's character — copy card descriptions from these configs:
      retail_standard 538-551 (noise 0.15, promo 0.1, stockout 0.02)
      holiday_rush    553-579 (CALENDAR-PINNED 2024-10-01..2024-12-31, the
                       docstring at 554-557 says "Pass an explicit
                       start_date/end_date to shift it" — the demo MUST send
                       the pinned window or the 2024 HolidayConfig spikes
                       never land in a today-anchored window)
      high_variance   581-595 (noise 0.4, anomaly 5% x3.0)
      stockout_heavy  597-610 (stockout 25%, behavior "zero")
      new_launches    612-628 (45-day launch ramps, native 100 products)
      sparse          630-642 (missing_combinations_pct=0.5, 3 gaps of 2-10d)
      showcase_rich   644-667 (5x15x180d, tuned noise 0.10)
      demo_minimal    669-692 (3x10x92d, tuned noise 0.10; >= 72d for non-NaN
                       WAPE with expanding/3-splits/h=14/min_train=30)

- file: app/features/demo/pipeline.py
  why: |
    _SCENARIO_SEED_PROFILE at 479-485 — TODAY only 3 entries
    (DEMO_MINIMAL/SHOWCASE_RICH/SPARSE as (stores, products, span_days)
    3-tuples); step_seed at 488-522 reads it with a demo_minimal fallback at
    492-495 and posts a today-anchored window at 496-497. REPLACE the tuple
    with a _SeedProfile NamedTuple carrying an optional pinned window.
    step_seed sends sparsity=0.0 (509) — keep; it preserves preset sparsity.
    _phase_table at ~2468-2551: ONLY `scenario is ScenarioPreset.SHOWCASE_RICH`
    gets the 24-row table; every other member gets the legacy 11 rows — the 5
    new presets need zero phase-table work.
    Backtest NaN gate at 763-765: all-NaN WAPE -> step FAIL (this is the
    sparse expected outcome documented in runbook #28).
    historical_backfill window gate at 829-833 (75 days, showcase_rich-only).

- file: app/features/seeder/service.py
  why: |
    _build_config_from_params at 202-247 — THE precedence contract: explicit
    stores/products/start_date/end_date ALWAYS override the preset (218-224);
    sparsity overrides only when params.sparsity > 0 (225-226), so the
    pipeline's 0.0 keeps the sparse preset's 50%-missing config. The demo can
    therefore demo-scale any preset without losing its character.
    _get_scenario_preset at 59-71 — any of the 8 names validates.

- file: app/features/seeder/schemas.py
  why: |
    GenerateParams at 78+ — scenario: str, stores ge=1 le=100,
    products ge=1 le=500, start_date/end_date. The demo seed body
    (pipeline.py:502-511) maps 1:1 onto this.

- file: frontend/src/types/api.ts
  why: |
    ScenarioPreset union at line 747 — widen to all 8 (keep the comment at
    745-746 pointing at the backend enum). DemoRunRequest at 769-775 needs no
    change beyond the union. WARNING: this file has MIXED CRLF/LF line
    endings — keep the edit surgical and check `git diff --stat` (a 1-line
    union change must not become a whole-file diff).

- file: frontend/src/components/demo/ScenarioPicker.tsx
  why: |
    The component to rewrite. Keep: ScenarioOption interface shape (11-16,
    extend with caveat fields), SCENARIO_OPTIONS array as the single source
    of card copy (18-37), the props interface verbatim (39-43), the
    "Scenario" label, font-mono preset id + text-muted-foreground description
    typography (69-72). Replace: the shadcn Select with a card grid.

- file: frontend/src/components/demo/PHASE_DEFS.ts
  why: |
    phaseDefsForScenario at 113-119 — branches ONLY on 'showcase_rich';
    every other value (incl. the 5 new ones) returns the legacy 11 steps.
    No change needed; ADD lockstep test coverage for the new values.

- file: frontend/src/pages/showcase.tsx
  why: |
    Wiring stays identical: scenario state from useDemoPipeline (106-108),
    start frame at 115, picker at 187. Optional: refresh the header copy at
    158-159 ("Pick a scenario to control depth..."). The Re-seed checkbox at
    205-215 is the trigger that makes a new preset actually take effect.

- file: frontend/src/hooks/use-demo-pipeline.ts
  why: |
    Default scenario 'demo_minimal' at line 200; createInitialSteps at 43-55
    derives idle cards from phaseDefsForScenario — all generic over the
    widened union; NO change needed (read to confirm, don't edit).

- file: frontend/src/components/demo/demo-step-card.tsx
  why: |
    Skip-status visual language to mirror on caveat badges: '⏭️' emoji
    (line 16) and muted-foreground accents (line 26). Semantic tokens only —
    never raw colors (shadcn rule).

- file: frontend/src/components/demo/ScenarioPicker.test.tsx
  why: |
    Current 3 tests query `getByRole('combobox')` — the rewrite REPLACES them
    (card grid has no combobox). Keep the vitest + @testing-library/react +
    afterEach(cleanup) harness pattern (lines 1-5).

- file: frontend/src/components/demo/PHASE_DEFS.test.ts
  why: Lockstep-test pattern to extend for the 5 new presets.

- file: app/features/demo/tests/test_pipeline.py
  why: |
    Patterns to reuse: _RecordingClient (1010-1052) records (method, path,
    json_body) per call — use it to assert step_seed's POST body per preset;
    _as_client cast helper (1055-1062); test_phase_table_sparse_matches_
    demo_minimal_shape (678-682) — extend to a parametrized all-presets test.

- file: frontend/src/components/ui/  (badge.tsx, card.tsx, tooltip.tsx)
  why: |
    Installed primitives for the card grid — compose from these; NO new
    shadcn component install is required. If one becomes necessary anyway,
    pin the CLI (`pnpm dlx shadcn@4.7.0 add ...`) — shadcn@latest 5.x writes
    a stub pnpm-workspace.yaml and skips the component (known local trap).

- file: docs/_base/RUNBOOKS.md
  why: |
    "Showcase page (/showcase) pipeline fails at step X" section — numbered
    entries 1..27 (last: 27 "Stop button used mid-run"). Append entry 28 in
    the same format: bold trigger, Cause, Fix. Also note the existing entry
    pattern for expected skips (#6 historical_backfill is the model).

- file: docs/_base/API_CONTRACTS.md
  why: |
    POST /demo/run row documents scenario as 'demo_minimal'|'showcase_rich'|
    'sparse' (PRP-38 note) and the WS /demo/stream start-frame line repeats
    it — both must say all 8 ScenarioPreset values are accepted (E2 #391
    additive note). E1 (#390) notes on the same row/section were just added —
    append, don't disturb them.

# External references (no new libraries; a11y + testing idioms only)
- url: https://www.w3.org/WAI/ARIA/apg/patterns/button/#:~:text=aria-pressed
  why: |
    Toggle-button group semantics for the card grid: role="group" +
    aria-label on the container, aria-pressed on each card button. Chosen
    over role="radiogroup"/role="radio" because the full radio pattern
    REQUIRES roving tabindex + arrow-key navigation; aria-pressed buttons
    are correct without custom key handling.
- url: https://testing-library.com/docs/queries/about/#priority
  why: Query the cards via getAllByRole('button', { pressed }) in the rewrite.

# Issue / initiative context
- url: https://github.com/w7-mgfcode/ForecastLabAI/issues/391
  why: The epic this PRP implements (Parallel; E1 #390 merged via PR #394).
- url: https://github.com/w7-mgfcode/ForecastLabAI/issues/389
  why: Umbrella — out-of-scope list (NO advanced seed-config UI, NO per-phase interactive config).
```

### Current Codebase tree (relevant subset)

```bash
app/features/demo/
├── pipeline.py            # _SCENARIO_SEED_PROFILE @479 (3 entries); step_seed @488; _phase_table @~2468
├── schemas.py             # DemoRunRequest.scenario: ScenarioPreset (full enum already) @60-64
└── tests/test_pipeline.py # _RecordingClient @1010; phase-table shape tests @602-701
app/shared/seeder/config.py    # ScenarioPreset @37-47; from_scenario @527-695
app/features/seeder/service.py # override precedence @202-247
frontend/src/
├── types/api.ts                          # ScenarioPreset union @747 (3 values; MIXED CRLF/LF)
├── components/demo/
│   ├── ScenarioPicker.tsx                # shadcn Select, 3 options
│   ├── ScenarioPicker.test.tsx           # 3 combobox-role tests (to be replaced)
│   ├── PHASE_DEFS.ts                     # phaseDefsForScenario @113-119 (no change)
│   ├── PHASE_DEFS.test.ts                # lockstep tests (extend)
│   └── demo-step-card.tsx                # skip visual language (⏭️, muted tokens)
├── hooks/use-demo-pipeline.ts            # default 'demo_minimal' @200 (no change)
└── pages/showcase.tsx                    # picker wiring @187 (≈no change)
```

### Desired Codebase tree (files added/modified)

```bash
app/features/demo/pipeline.py             # MOD — _SeedProfile NamedTuple; 8-entry _SCENARIO_SEED_PROFILE; step_seed pinned-window branch
app/features/demo/tests/test_pipeline.py  # MOD — profile exhaustiveness, per-preset POST-body, parametrized phase-table shape
frontend/src/types/api.ts                 # MOD — 8-value ScenarioPreset union (surgical edit)
frontend/src/components/demo/ScenarioPicker.tsx       # MOD — card grid, 8 SCENARIO_OPTIONS + caveats, same props
frontend/src/components/demo/ScenarioPicker.test.tsx  # MOD — rewritten for the card grid
frontend/src/components/demo/PHASE_DEFS.test.ts       # MOD — lockstep coverage for the 5 new presets
frontend/src/pages/showcase.tsx           # MOD (optional, 1-2 lines) — header copy mentions 8 presets
docs/_base/API_CONTRACTS.md               # MOD — full scenario union on /demo/run + WS start frame
docs/_base/RUNBOOKS.md                    # MOD — showcase entry #28 (preset expected-outcome matrix)
```

### Known Gotchas & Library Quirks

```python
# CRITICAL — holiday_rush is CALENDAR-PINNED (config.py:553-579). Its
#   HolidayConfig rows are fixed 2024 dates; a today-anchored window never
#   contains them and the preset silently degrades to mild Q4 seasonality.
#   The demo seed MUST send start_date=2024-10-01, end_date=2024-12-31 for
#   this preset (the _SeedProfile pinned-window field exists for exactly this).

# CRITICAL — seeder override precedence (service.py:213-226): request
#   stores/products/start/end ALWAYS override the preset; sparsity only
#   overrides when > 0. The pipeline sends sparsity=0.0 — DO NOT "fix" that
#   to a truthy value or the sparse preset's 50%-missing config gets replaced.

# CRITICAL — sparse can legitimately FAIL the run: the grain discovery picks
#   the first store/product (pipeline.py:540-561); with 50% missing combos +
#   gaps that grain can have too-thin history -> features/backtest fail, or
#   all-NaN WAPE -> step_backtest FAIL (763-765). E2 documents this (card
#   caveat + runbook #28); it does NOT change pipeline semantics.

# CRITICAL — every new seed profile window must be >= 75 days, or a later
#   showcase_rich run with skip_seed=true trips the historical_backfill gate
#   (pipeline.py:829-833). Chosen profiles: 180d (and holiday_rush's pinned
#   92-day-inclusive window) all clear it.

# GOTCHA — frontend type gates: `pnpm tsc --noEmit` exits 1 with NO output
#   (solution-style tsconfig — vacuous), and `pnpm tsc -b` currently fails
#   with 24 PRE-EXISTING errors on dev, none in demo components (verified
#   2026-06-12). Gate on `pnpm lint && pnpm test --run`; for types, require
#   "no NEW tsc -b errors mentioning files you touched":
#   cd frontend && pnpm tsc -b 2>&1 | grep -E "ScenarioPicker|types/api|PHASE_DEFS|showcase"   # expect empty

# GOTCHA — frontend/src/types/api.ts has MIXED CRLF/LF line endings. Edit the
#   single union line only; verify `git diff --stat` shows ±1-2 lines.

# GOTCHA — the existing ScenarioPicker tests query getByRole('combobox');
#   after the card rewrite that role disappears. Rewrite the tests with
#   getAllByRole('button') / aria-pressed queries; keep afterEach(cleanup).

# GOTCHA — shadcn: compose the grid from the INSTALLED primitives (badge,
#   card, tooltip — frontend/src/components/ui/). No radio-group component is
#   installed; use aria-pressed buttons (see W3C APG ref) instead of
#   installing one. If you DO add a component, pin `pnpm dlx shadcn@4.7.0`
#   (5.x writes a stub pnpm-workspace.yaml and skips the component) and use
#   per-component @radix-ui/react-X imports, not the radix barrel.

# GOTCHA — semantic tokens only on cards (border-primary, bg-muted,
#   text-muted-foreground); never raw colors (bg-blue-500). Selected state:
#   border + ring with primary tokens; caveat badge mirrors the step-card
#   skip language ('⏭️' + muted tokens, demo-step-card.tsx:16,26).

# GOTCHA — mypy --strict AND pyright --strict gate the pipeline.py change.
#   A NamedTuple with a default (window: tuple[date, date] | None = None)
#   is fine on 3.12; annotate fully.

# CONVENTION — commits (every one references #391, no AI trailer):
#   feat(api): extend demo seed profiles to all scenario presets (#391)
#   feat(ui): expose all eight scenario presets as guided cards (#391)
#   docs(api): document full scenario union and preset outcomes (#391)
#   docs(repo): track showcase workspace e2 prp (#391)
#   Branch off dev: feat/showcase-preset-exposure (<=50 chars, kebab).

# RUNTIME-VERIFICATION LOG (per prp-create step 3):
#   - No new third-party API claims — the PRP cites only in-repo patterns
#     (NamedTuple defaults are stdlib; aria-pressed is plain DOM).
#   - `pnpm test --run src/components/demo/ScenarioPicker.test.tsx` → 3 passed
#     (verified 2026-06-12; the vitest harness works as cited).
#   - `pnpm tsc --noEmit` exit 1 (silent) / `pnpm tsc -b` 24 pre-existing
#     errors, none in demo components (verified 2026-06-12).
#   - Seeder precedence + pinned-window behavior read directly from
#     service.py:202-247 and config.py:553-579 (not inferred).
```

## Implementation Blueprint

### Data models and structure

```python
# app/features/demo/pipeline.py — replace the 3-tuple profile (lines 479-485)
class _SeedProfile(NamedTuple):
    """Demo-scaled seed profile for one scenario preset.

    The /seeder/generate request overrides preset dims/window by design
    (app/features/seeder/service.py:213-226) while preserving the preset's
    behavioral character (noise, promos, stockouts, sparsity, launch ramps).
    ``window`` pins a fixed calendar range (holiday_rush); when None the
    window is ``span_days`` back from today.
    """
    stores: int
    products: int
    span_days: int
    window: tuple[date, date] | None = None

_SCENARIO_SEED_PROFILE: dict[ScenarioPreset, _SeedProfile] = {
    ScenarioPreset.DEMO_MINIMAL: _SeedProfile(DEMO_SEED_STORES, DEMO_SEED_PRODUCTS, DEMO_SEED_SPAN_DAYS),
    ScenarioPreset.SHOWCASE_RICH: _SeedProfile(5, 15, 180),
    ScenarioPreset.SPARSE: _SeedProfile(DEMO_SEED_STORES, DEMO_SEED_PRODUCTS, DEMO_SEED_SPAN_DAYS),
    # E2 (#391) — demo-scaled profiles; preset character comes from
    # SeederConfig.from_scenario, dims/window from this request (precedence
    # contract: app/features/seeder/service.py:213-226). All windows >= 75d
    # so a later showcase_rich skip_seed run clears the backfill gate.
    ScenarioPreset.RETAIL_STANDARD: _SeedProfile(5, 15, 180),
    ScenarioPreset.HIGH_VARIANCE: _SeedProfile(5, 15, 180),
    ScenarioPreset.STOCKOUT_HEAVY: _SeedProfile(5, 15, 180),
    ScenarioPreset.NEW_LAUNCHES: _SeedProfile(5, 25, 180),   # extra products for launch variety (native preset uses 100)
    # Calendar-pinned: the preset's HolidayConfig spikes are fixed 2024 dates
    # (config.py:553-579) — a today-anchored window would never contain them.
    # span_days=91 mirrors DEMO_SEED_SPAN_DAYS symmetry; it is dead data when
    # window is set (the pinned range is 92 days inclusive, delta 91).
    ScenarioPreset.HOLIDAY_RUSH: _SeedProfile(5, 15, 91, window=(date(2024, 10, 1), date(2024, 12, 31))),
}

# step_seed (488-522) — window resolution becomes:
#   profile = _SCENARIO_SEED_PROFILE.get(ctx.scenario, _SeedProfile(DEMO_SEED_STORES, DEMO_SEED_PRODUCTS, DEMO_SEED_SPAN_DAYS))
#   if profile.window is not None: seed_start, seed_end = profile.window
#   else: seed_end = datetime.now(UTC).date(); seed_start = seed_end - timedelta(days=profile.span_days)
# Everything else in the POST body stays byte-identical.
```

```tsx
// frontend/src/components/demo/ScenarioPicker.tsx — extended option shape
interface ScenarioOption {
  value: ScenarioPreset
  title: string                 // business-friendly, e.g. 'Holiday rush'
  description: string           // dims x window + character, one line
  estimatedWallClock: string
  caveat?: string               // expected-skip / pinned-window note
  caveatKind?: 'expected-skip' | 'info'
}

// The 8 cards (single source of card copy — descriptions are truthful to the
// _SeedProfile the seed step posts, NOT to the preset's native full-size config):
//  demo_minimal   'Demo minimal'    '3 stores x 10 products x 92 days — fast smoke loop'        '~60 s'
//  showcase_rich  'Showcase rich'   '5 x 15 x 180 days — full 24-step flow, V1+V2 modeling'     '~3 min'
//                 caveat(info): 'Knowledge/agent steps skip without provider keys'
//  retail_standard 'Retail standard' '5 x 15 x 180 days — steady demand, light promos'          '~90 s'
//  holiday_rush   'Holiday rush'    '5 x 15 x Oct-Dec 2024 — Black Friday/Christmas spikes'     '~90 s'
//                 caveat(info): 'Seeds a pinned 2024 window (calendar-pinned holidays)'
//  high_variance  'High variance'   '5 x 15 x 180 days — noisy demand with anomaly spikes'      '~90 s'
//  stockout_heavy 'Stockout heavy'  '5 x 15 x 180 days — 25% stockout days zero the sales'      '~90 s'
//  new_launches   'New launches'    '5 x 25 x 180 days — 45-day product launch ramps'           '~2 min'
//  sparse         'Sparse'          '3 x 10 x 92 days — 50% missing grains + random gaps'       '~90 s'
//                 caveat(expected-skip): '⏭️ May fail at features/backtest (NaN WAPE) — expected; see runbook'
//
// Markup sketch (semantic tokens only; props interface UNCHANGED):
// <div className="flex flex-col gap-2">
//   <label className="text-sm font-medium">Scenario</label>
//   <div role="group" aria-label="Scenario" className="grid grid-cols-2 gap-2 xl:grid-cols-4">
//     {SCENARIO_OPTIONS.map((opt) => (
//       <button key={opt.value} type="button" aria-pressed={opt.value === value}
//               disabled={disabled} onClick={() => onChange(opt.value)}
//               className={cn('rounded-lg border p-3 text-left transition-colors',
//                             'hover:bg-muted/50 disabled:opacity-50 disabled:pointer-events-none',
//                             opt.value === value ? 'border-primary ring-1 ring-primary' : 'border-border')}>
//         <div className="flex items-center justify-between gap-2">
//           <span className="text-sm font-medium">{opt.title}</span>
//           <span className="font-mono text-xs text-muted-foreground">{opt.value}</span>
//         </div>
//         <p className="mt-1 text-xs text-muted-foreground">{opt.description} · {opt.estimatedWallClock}</p>
//         {opt.caveat && <Badge variant="outline" className="mt-2 text-xs text-muted-foreground">{opt.caveat}</Badge>}
//       </button>
//     ))}
//   </div>
//   <p className="text-xs text-muted-foreground">
//     Tick <span className="font-medium">Re-seed first</span> when switching presets — without it the run reuses the currently seeded dataset.
//   </p>
// </div>
```

### List of tasks (dependency order)

```yaml
Task 1 — branch & issue hygiene:
  RUN: git switch dev && git pull && git switch -c feat/showcase-preset-exposure
  VERIFY: gh issue view 391 --json state   # open

Task 2 — MODIFY app/features/demo/pipeline.py (backend first — it defines the truthful card copy):
  - ADD `from typing import NamedTuple` is NOT needed (typing imports exist) — check the
    import block at 22-44 and extend `from typing import Any` appropriately (NamedTuple).
  - REPLACE the dict at 479-485 with _SeedProfile + 8 entries (blueprint above);
    keep the `.get(...)` fallback in step_seed (a future 9th enum member must not crash).
  - MODIFY step_seed window resolution (pinned-window branch, blueprint above).
  - PRESERVE the POST body keys byte-identically (sparsity=0.0 stays).

Task 3 — MODIFY app/features/demo/tests/test_pipeline.py:
  - ADD test_scenario_seed_profile_covers_every_preset:
      assert set(pipeline._SCENARIO_SEED_PROFILE) == set(ScenarioPreset)
  - ADD test_step_seed_holiday_rush_posts_pinned_window:
      ctx = DemoContext(seed=42, skip_seed=False, reset=False, scenario=ScenarioPreset.HOLIDAY_RUSH)
      client = _RecordingClient(None, responses={("POST", "/seeder/generate"): {"records_created": {"sales": 1}}})
      await pipeline.step_seed(ctx, _as_client(client))
      body = client.calls[0][2]; assert body["start_date"] == "2024-10-01"; assert body["end_date"] == "2024-12-31"; assert body["scenario"] == "holiday_rush"
  - ADD test_step_seed_retail_standard_posts_demo_scaled_profile:
      same harness; assert stores=5, products=15, and
      date.fromisoformat(end) - date.fromisoformat(start) == timedelta(days=180)
  - EXTEND test_phase_table_sparse_matches_demo_minimal_shape into a
    @pytest.mark.parametrize over [RETAIL_STANDARD, HOLIDAY_RUSH, HIGH_VARIANCE,
    STOCKOUT_HEAVY, NEW_LAUNCHES, SPARSE] asserting _phase_table(p) shape ==
    _phase_table(DEMO_MINIMAL) shape (keep the original test name working or
    replace it wholesale — your call; do not lose sparse coverage).

Task 4 — MODIFY frontend/src/types/api.ts (line 747, surgical):
  - ScenarioPreset union -> all 8 values, alphabetic except keep the 3 existing
    first if you prefer minimal diff; update the comment to say "all 8 members".
  - VERIFY: git diff --stat frontend/src/types/api.ts   # 1 file, ~2 lines

Task 5 — REWRITE frontend/src/components/demo/ScenarioPicker.tsx:
  - Blueprint above. Props interface UNCHANGED. Single SCENARIO_OPTIONS array
    of 8 with caveat fields. aria-pressed button grid in role="group".
  - Import Badge from '@/components/ui/badge' and cn from '@/lib/utils'
    (verify the cn helper path with grep before importing).
  - Remove the now-unused Select imports.

Task 6 — REWRITE frontend/src/components/demo/ScenarioPicker.test.tsx:
  - renders all 8 cards: getAllByRole('button').length === 8 and each preset id visible
  - click fires onChange: render with onChange spy, click the 'retail_standard' card,
    expect spy called with 'retail_standard'
  - selected card aria-pressed: render value="showcase_rich"; the showcase_rich
    button has aria-pressed="true", others "false"
  - disabled: all 8 buttons disabled when disabled prop set
  - sparse caveat: the sparse card's text contains 'expected' (caveat badge)
  - holiday_rush caveat: text contains '2024'

Task 7 — MODIFY frontend/src/components/demo/PHASE_DEFS.test.ts:
  - ADD a parametrized (it.each) lockstep case: for each of the 5 new presets,
    phaseDefsForScenario(p) deep-equals phaseDefsForScenario('demo_minimal').

Task 8 — (optional, 1-2 lines) MODIFY frontend/src/pages/showcase.tsx:
  - Header copy at 158-159: "Pick a scenario to control depth and data shape —
    all eight seeder presets are available." Keep the rest untouched.

Task 9 — docs:
  - docs/_base/API_CONTRACTS.md: on the POST /demo/run row AND the WS
    /demo/stream start-frame line, append: "E2 (#391) — `scenario` accepts all
    8 `ScenarioPreset` values (retail_standard / holiday_rush / high_variance /
    stockout_heavy / new_launches / sparse / demo_minimal / showcase_rich);
    only `showcase_rich` changes the step table (24 rows), every other preset
    runs the legacy 11-row flow."
  - docs/_base/RUNBOOKS.md: append showcase entry 28 following entry 6's
    expected-skip format: "**A newly exposed preset run ends red/skipped
    (E2 #391)** — per-preset expected outcomes: sparse may FAIL at
    features/backtest (50% missing grains / NaN WAPE — expected, the card says
    so); holiday_rush seeds a pinned Oct–Dec 2024 window (today-anchored data
    disappears — re-seed to switch back); all other presets are expected
    green on the 11-step flow. Cause/Fix lines per the section's format."

Task 10 — gates, dogfood, commit, PR:
  - Backend gates + frontend lint/test (Validation Loop below).
  - Level 4 browser dogfood (mandatory per .claude/rules/ui-design.md — a UI
    change is NOT done until exercised in a real browser).
  - git diff --stat  # surgical-diff check (api.ts CRLF trap)
  - Commits per the convention block; PR into dev titled
    "feat(ui): showcase workspace full preset exposure (#391)".
```

### Integration Points

```yaml
DATABASE: none — no schema change, no migration.
CONFIG: none — no new settings or env vars.
ROUTES: none — DemoRunRequest already accepts the full enum (schemas.py:60-64).
WS CONTRACT: unchanged shape; only the accepted scenario value set is documented wider.
FRONTEND: ScenarioPicker internals + types/api.ts union; showcase.tsx wiring untouched.
DOCS: API_CONTRACTS scenario union; RUNBOOKS entry #28. (DOMAIN_MODEL/RUNBOOKS
  full sweep belongs to the E5 release gate — do not scope-creep.)
```

## Validation Loop

### Level 1: Syntax & Style

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/ && uv run pyright app/          # both --strict, gate merge
cd frontend && pnpm lint
# Types: no NEW errors mentioning touched files (24 pre-existing tsc -b errors exist on dev):
cd frontend && pnpm tsc -b 2>&1 | grep -E "ScenarioPicker|types/api|PHASE_DEFS|pages/showcase" ; echo "exit=$? (1 = no matches = good)"
```

### Level 2: Unit Tests

```bash
uv run pytest app/features/demo -v -m "not integration"   # incl. the new profile/seed/phase tests
cd frontend && pnpm test --run src/components/demo/        # picker rewrite + lockstep
cd frontend && pnpm test --run                             # full frontend suite
```

### Level 3: Integration (real Postgres; demo slice unaffected but run it)

```bash
docker compose up -d && uv run alembic upgrade head
uv run pytest app/features/demo -v -m integration          # E1 suites still green (no schema change)
```

### Level 4: Browser dogfood (uvicorn :8123 + vite :5173)

```bash
uv run uvicorn app.main:app --port 8123 &
cd frontend && ./node_modules/.bin/vite --host 0.0.0.0 &   # bypasses pnpm 11 depsStatusCheck
# In a real browser (webapp-testing skill / agent-browser; on this host Playwright
# needs executable_path=/snap/bin/chromium — see memory note in RUNBOOKS context):
#  1. /showcase shows 8 scenario cards; sparse carries the expected-skip badge,
#     holiday_rush the pinned-2024 badge; cards disable while running.
#  2. Pick retail_standard + tick "Re-seed first" -> Run: 11 steps, green; the
#     seed card detail says "retail_standard: 5 stores x 15 products".
#  3. Pick holiday_rush + Re-seed -> Run: green; after the run,
#     GET /seeder/status shows date_range 2024-10-01..2024-12-31.
#  4. Pick demo_minimal + Re-seed -> Run: green (restores the default dataset).
#  5. (Optional, documented outcome) sparse + Re-seed: green OR a features/
#     backtest fail matching runbook #28 — either outcome is a pass for E2.
```

## Final validation Checklist

- [ ] Backend gates: `uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pyright app/ && uv run pytest -v -m "not integration"`
- [ ] Frontend: `pnpm lint && pnpm test --run` green; no NEW tsc -b errors in touched files
- [ ] `_SCENARIO_SEED_PROFILE` exhaustive over the enum (test enforces)
- [ ] holiday_rush posts the pinned 2024 window; retail_standard posts 5×15×180d (tests enforce)
- [ ] 8 cards render; selection/disabled/aria-pressed/caveats covered by tests
- [ ] Lockstep: backend parametrized phase-table test + frontend PHASE_DEFS it.each both green
- [ ] Browser dogfood (Level 4) performed in a real browser — not just tests
- [ ] `git diff --stat` surgical (especially frontend/src/types/api.ts — mixed CRLF/LF)
- [ ] API_CONTRACTS + RUNBOOKS #28 updated additively
- [ ] Commits `feat(api)/feat(ui)/docs(api)/docs(repo): ... (#391)`, no AI trailer; PR into dev

---

## Anti-Patterns to Avoid

- ❌ Don't change pipeline semantics for sparse (no NaN→skip rework) — E2 is labeling + docs; a graceful-skip would mask real regressions on healthy presets.
- ❌ Don't touch `_phase_table` / `phaseDefsForScenario` — the 5 new presets already get the legacy 11-step flow from the existing else-branch.
- ❌ Don't seed full-size preset dims (10×50×365 ≈ 183k rows) — demo profiles stay laptop-friendly; the request-override precedence exists precisely for this.
- ❌ Don't break the ScenarioPicker props interface — showcase.tsx, use-demo-pipeline, and RunHistoryStrip are all generic over the widened union and must not need edits.
- ❌ Don't install a shadcn radio-group (or anything) when aria-pressed buttons suffice; if you must, pin shadcn@4.7.0.
- ❌ Don't hand-set raw Tailwind colors — semantic tokens only.
- ❌ Don't ship the UI without a real-browser check — `.claude/rules/ui-design.md` makes that a hard requirement.
- ❌ Don't widen the seeder HTTP schema or add seed-config knobs to the UI — explicitly out of scope per umbrella #389.

## Confidence Score

**8.5/10** for one-pass implementation success. Every change has a verified
in-repo precedent (the profile dict + step_seed already exist; _RecordingClient
covers the POST-body assertions; the lockstep test pair already gates phase
shape; the card grid composes from installed primitives with the props
interface frozen). The two judgment calls — demo-scaled profile sizes and the
holiday_rush pinned window — are decided above with rationale and enforced by
tests, so a disagreement costs a constant tweak, not a rework. The −1.5 is
UI-surface risk: card-grid styling/dogfood may need an iteration pass, and the
sparse Level-4 outcome is intentionally non-deterministic (either result is
documented as a pass).
