name: "PRP — Reliability E4: move ModelFamily to app/shared and retire the forecasting↔registry lazy-import workarounds"
description: |
  Parallel epic of umbrella #380 (platform reliability hardening), after Foundation E1 (#334).
  Issue: #268 · Branch: `refactor/shared-model-taxonomy` off `dev` · Commit scope: `forecast,registry`
  (backend-only — zero frontend changes, zero DB migration, zero API contract change).

---

## Goal

`ModelFamily` (enum) and `model_family_for()` (its canonical model_type→family map) live in the
forecasting slice today. `app/features/registry/schemas.py:27` must import `ModelFamily` **eagerly**
(Pydantic v2 resolves a `@computed_field`'s return-type annotation when it builds the serialization
schema), which is a direct violation of the vertical-slice invariant (`app/features/X` may NOT
import `app/features/Y`) and the proximate cause of the documented lazy-import workaround web
(6 mapped sites, NOTE comments in 4 files, and the alembic cold-boot trap that bit PRP-31).

**Deliverable:**
1. A new neutral module `app/shared/model_taxonomy.py` owning `ModelFamily`, `_MODEL_FAMILY_MAP`,
   and `model_family_for()` (moved verbatim, logger via `app.core.logging.get_logger`).
2. Back-compat re-exports from the two old homes (`forecasting/schemas.py`,
   `forecasting/feature_metadata.py`) using the redundant-alias idiom (`import X as X`) so every
   existing importer — including both untouched test suites — keeps resolving under
   `mypy --strict` (no_implicit_reexport).
3. The 6 mapped lazy-import sites resolved per the verdict table below: 5 retired (promoted to
   module scope), 1 kept-but-re-documented (the genuinely mutual jobs↔forecasting pair).
4. A new test suite `app/shared/tests/test_model_taxonomy.py` that locks the mapping, the enum
   identity across re-export paths, the JSON-schema contract, and — the spec for this bug class —
   subprocess **cold-boot probes** that import the worst-case entry points in fresh interpreters
   (pytest's in-process import order masks these cycles; a subprocess is the only honest in-suite check).
5. `docs/_base/ARCHITECTURE.md` cross-slice pattern section updated: the stale forecasting
   precedent replaced, this refactor recorded as the "resolved cycle" example.

**Success definition (umbrella #380 acceptance row):** `ModelFamily` imports resolve from
`app/shared/`; **zero** lazy-import NOTE comments reference the forecasting↔registry ModelFamily
cycle; `alembic upgrade head` cold-boots clean (CI migration-check + local smoke); all five
validation gates green; both pre-existing test suites (`test_feature_metadata.py`,
`test_schemas.py`) pass **untouched**.

## Why

- **The cycle is real and armed.** Verified 2026-06-11: `alembic/env.py:23` does
  `from app.features.registry import models` → `registry/__init__.py` eagerly imports
  `registry.schemas` → `registry/schemas.py:27` imports `app.features.forecasting.schemas`,
  which first executes `forecasting/__init__.py` → which eagerly imports `forecasting/service.py`.
  If anyone promotes `forecasting/service.py`'s registry imports to module scope today,
  `registry.service:29` re-enters the **partially initialized** `registry.schemas` →
  `ImportError` at alembic cold-boot. PRP-31 hit exactly this; the lazy imports were the patch,
  not the fix (memory anchor: `[[computed-field-cross-slice-cycle]]`, tracking issue #260).
- **The workaround metastasized.** The discipline got cargo-culted into model_selection and batch
  ("mirror service.py", "precedent: forecasting/service.py:786-787" — a line number that is
  already stale), so every new slice pays a tax for a cycle only one edge causes.
- **Umbrella #380 acceptance** explicitly lists: "`ModelFamily` imports resolve from `app/shared/`;
  zero lazy-import NOTE comments reference the forecasting↔registry ModelFamily cycle; `alembic
  upgrade head` cold-boots clean in CI migration-check (#268 closed)".
- **Origin:** CodeRabbit #3270767554 on PR #266 flagged the slice-invariant violation; issue #268
  deferred it behind this PRP.

## What

### The cycle topology (verified, this is the whole bug)

```
alembic/env.py:23  ──►  from app.features.registry import models
  └─► app/features/registry/__init__.py        (eagerly imports schemas + service + storage)
        └─► registry/schemas.py:27             from app.features.forecasting.schemas import ModelFamily
              └─► app/features/forecasting/__init__.py   (eagerly imports forecasting.service!)
                    └─► forecasting/service.py
                          └─► [IF EAGER] registry.service:29 → from registry.schemas import ...
                                └─► registry.schemas is PARTIALLY INITIALIZED (still on line 27)
                                      └─► ImportError: cannot import name ... from partially
                                          initialized module  ← the alembic cold-boot crash
```

Post-move: `registry/schemas.py` imports only `app.shared.model_taxonomy` → the
registry→forecasting edge disappears entirely → every chain terminates in `app/shared` /
`app/core` → `forecasting/service.py` may import `RegistryService` eagerly. Verified by tracing
every entry order (alembic-first, forecasting-first, main) against the module-scope import lists
of all involved slices (see verdict table).

### The 6 mapped import sites — verdicts

| # | Site | Today | Verdict | Why |
|---|------|-------|---------|-----|
| S1 | `registry/schemas.py:27` (eager `ModelFamily` from forecasting) + `:175` (lazy `model_family_for` inside the computed field) | THE cycle-causing edge | **RETIRE** — both become module-scope imports from `app.shared.model_taxonomy` | Removes the only registry→forecasting edge |
| S2 | `forecasting/service.py:967-968` — lazy `RunStatus` + `RegistryService` inside `get_feature_metadata_for_run` | workaround for S1 | **RETIRE** — promote to module scope | Post-move chain: forecasting.service → registry pkg `__init__` → schemas (shared-only) + service + storage → terminates. Verified no back-edge. |
| S3 | `forecasting/service.py:1053-1054` — lazy `JobStatus`/`JobType`/`JobService` inside `get_feature_metadata_for_job` | lumped into the same NOTE | **KEEP lazy, REWRITE comment** | Different cycle: `jobs/service.py:435` and `:545` lazily import `ForecastingService` back (call-time). The pair is mutually dependent — at least one side must stay lazy forever. NOT broken by this refactor; the comment must stop blaming ModelFamily. |
| S4 | `model_selection/capabilities.py:135` — lazy `model_family_for` inside `build_model_catalog` | "mirror service.py" | **RETIRE** — module-scope `from app.shared.model_taxonomy import model_family_for` | Pure shared import; also update the module-docstring provenance note (lines 9-10). |
| S5 | `model_selection/service.py:1077-1083` — lazy `AliasCreate`/`RunCreate`/`RunStatus`/`RunUpdate` + `RegistryService` inside `promote_champion_selection` | defensive mirror | **RETIRE** — promote to module scope | Verified: nothing in registry imports model_selection; `model_selection/models.py` imports only core+shared (alembic path clean); `model_selection/__init__.py` is docstring-only. Chain terminates post-move. No name collisions at module scope (checked). |
| S6 | `batch/service.py:292-294` — lazy `JobStatus`/`JobCreate`/`JobService` inside `_execute_item` | comment cites "alembic cold-boot cycle" + stale precedent line | **RETIRE** — promote to module scope | Verified: nothing anywhere imports batch except `app/main.py` (routes); jobs slice has ZERO eager cross-slice imports; jobs never imports batch. Permanently safe. The stale comment goes away with it. |

Counterpart sites that stay lazy **by design** (out of the 6, do not touch the code):
`jobs/service.py:435,545` (lazy `ForecastingService` — the other half of the S3 pair) and
`model_selection/service.py:380,396,916,972,1036` (lazy `ForecastingService` — heavy module,
different dependency; eagerizing is possible post-move but is pointless churn here).

### Out of scope

- **No API change.** `ModelFamily`'s JSON schema derives from the class name and values
  (`title: "ModelFamily"`, `enum: ["baseline","tree","additive"]`) — verified unchanged by a move
  (see Gotcha 6). `RunResponse.model_family` keeps its shape; the OpenAPI *description* string
  changes because the stale lazy-import docstring is rewritten (descriptions leak docstrings) —
  harmless, documented here so nobody chases it.
- **No DB migration** — `ModelFamily` is never persisted (computed field; not in any ORM model).
- **No pickle/artifact concern** — verified `ModelFamily` instances never enter joblib bundles
  (`grep -rn "ModelFamily" app/features/forecasting/persistence.py` → no hits), so relocating the
  class cannot break unpickling of existing artifacts.
- **The data_platform cross-slice ORM imports** — sibling CodeRabbit flag, tracked separately
  (memory anchor `[[data-platform-shared-orm-layer]]`); do NOT touch.
- **No ADR.** Issue #268 said "likely an ADR if the chosen module isn't an obvious fit" —
  `app/shared/` is the documented home for cross-cutting code (AGENTS.md § Architecture;
  precedent: `app/shared/feature_frames/` already owns the cross-slice `FeatureGroup`). Obvious fit.
- **jobs↔forecasting mutual dependency** — a real design wart; needs an interface/abstraction PRP
  of its own if it ever matters. This PRP only re-documents it honestly.

### Success Criteria

- [ ] `app/shared/model_taxonomy.py` exists; `from app.shared.model_taxonomy import ModelFamily,
      model_family_for` works; mapping behavior byte-identical (same 11 entries, same BASELINE
      fallback + warning event `forecasting.unknown_model_family`)
- [ ] `from app.features.forecasting.schemas import ModelFamily` and
      `from app.features.forecasting.feature_metadata import model_family_for` still resolve and
      return **the same objects** (`is` identity) — both pre-existing test suites pass untouched
- [ ] `grep -rn "from app.features.forecasting" app/features/registry/` → zero hits
- [ ] Zero comments in `app/` reference the ModelFamily/registry cycle as a reason for laziness
      (`grep -rn "ModelFamily" app/ --include="*.py" | grep -i "lazy\|cycle"` → only
      model_taxonomy.py's own docstring narrating the history)
- [ ] S2/S4/S5/S6 imports are at module scope; S3 stays lazy with a comment naming
      `jobs/service.py:435,545` as the counterpart
- [ ] Cold-boot probes green: fresh-interpreter `from app.features.registry import models`
      (alembic shape), `import app.features.forecasting`, `import app.main`; plus
      `uv run alembic upgrade head` against the local DB
- [ ] All gates green: ruff + ruff format, mypy --strict, pyright --strict, pytest unit;
      targeted integration tests pass

## All Needed Context

### Documentation & References

```yaml
# MUST READ — why each mechanism behaves the way it does
- url: https://docs.python.org/3/reference/import.html#regular-packages
  why: Importing app.features.forecasting.schemas FIRST executes the package __init__.py —
       this is what arms the cycle (forecasting/__init__ eagerly imports service.py). Any
       "module X only imports Y" reasoning must account for package __init__ side effects.

- url: https://mypy.readthedocs.io/en/stable/config_file.html#confval-no_implicit_reexport
  why: pyproject sets mypy strict=true which enables no_implicit_reexport — a plain
       `from shared import ModelFamily` in forecasting/schemas.py would NOT legally re-export;
       downstream `from forecasting.schemas import ModelFamily` would be a mypy error.
       The redundant alias `import X as X` is the sanctioned re-export idiom (also recognized
       by pyright and by ruff F401).

- url: https://docs.pydantic.dev/latest/concepts/fields/#the-computed_field-decorator
  why: The computed_field return annotation is resolved when Pydantic builds the model's
       serialization schema — ModelFamily must be a REAL runtime import in registry/schemas.py
       (the existing comment at lines 20-26 says exactly this; keep that fact in the new comment).

# MUST READ — codebase files (the mutation surface)
- file: app/features/forecasting/schemas.py
  why: Lines 612-629 — section header + ModelFamily class to DELETE (move). Line 677
       FeatureMetadataResponse.model_family keeps using the name. Head shows import style +
       `from __future__ import annotations`. 724 lines total.

- file: app/features/forecasting/feature_metadata.py
  why: Lines 38-73 — _MODEL_FAMILY_MAP + model_family_for() to DELETE (move verbatim).
       Line 30 imports FeatureImportanceItem + ModelFamily from schemas (ModelFamily becomes
       re-export only — nothing else in this file uses it after the move). Line 35 shows the
       feature-module logger idiom (structlog.get_logger); the shared module uses the
       app.core.logging.get_logger idiom instead. 232 lines total.

- file: app/features/registry/schemas.py
  why: Lines 9 (from __future__ import annotations), 20-27 (the cycle comment + eager import
       to REPLACE), 129-137 (RunResponse docstring citing the feature_metadata path — update),
       166-177 (the computed field + lazy import to simplify).

- file: app/features/forecasting/service.py
  why: Lines 34-53 (module import block — where the promoted registry imports land, isort-sorted),
       55-61 (the NOTE block to REWRITE — it currently blames ModelFamily), 966-968 (S2 lazy
       imports to delete), 974/984-985 (RunStatus/model_family_for usage that keeps working),
       1052-1054 (S3 — KEEP, new comment).

- file: app/features/model_selection/capabilities.py
  why: Lines 1-22 module docstring (provenance bullet at 9-10 says "lazy cross-slice import …" —
       update), 133-135 (S4 lazy import + comment to delete; promote to module scope next to the
       existing `from app.features.model_selection.schemas import …` block).

- file: app/features/model_selection/service.py
  why: Lines 28-60 module import block (promotion target), 1077-1083 (S5 lazy imports to delete).
       Names are used at 1095-1138 — no module-scope collisions (verified).

- file: app/features/batch/service.py
  why: Lines 286-295 (S6 — docstring with the stale "alembic cold-boot cycle / precedent
       forecasting/service.py:786-787" claim + lazy imports). Promote imports; fix docstring.

- file: app/shared/feature_frames/__init__.py
  why: The house precedent for a shared package consumed cross-slice (FeatureGroup already
       crosses slices from here). model_taxonomy.py follows the same "leaf-level shared module,
       imported explicitly by path" style. Do NOT add to app/shared/__init__.py (feature_frames
       isn't there either).

- file: app/features/scenarios/feature_frame.py
  why: Lines 41-94 — the house precedent for back-compat re-exports after relocating symbols
       (re-export + explanatory comment). This PRP uses the redundant-alias variant because
       forecasting/schemas.py has no __all__ today and only two names move.

- file: app/shared/feature_frames/tests/test_contract.py
  why: Shared-package test conventions (tests/ subdir WITH __init__.py — verified all tests
       dirs in this repo have one; plain functions; S101 et al. ignored via per-file-ignores).

- file: tests/test_e2e_demo.py
  why: Lines 102, 152 — the house pattern for subprocess in tests:
       `subprocess.run(...)  # noqa: S603 — internal command, trusted args` (ruff S is enabled;
       S603 fires on subprocess use; this is the sanctioned suppression).

- file: app/features/forecasting/tests/test_feature_metadata.py
  why: Lines 75-108 — the 6 existing model_family_for tests. They import via the OLD paths and
       MUST stay untouched and green (they are the back-compat proof). Mirror their style for
       the new shared suite.

- file: app/features/registry/tests/test_schemas.py
  why: Line 9 imports ModelFamily from forecasting.schemas; the TestRunResponseModelFamily class
       (~lines 389-450) exercises the computed field. Untouched + green = back-compat proof #2.

- file: docs/_base/ARCHITECTURE.md
  why: Section "### Cross-slice read-only import pattern" (line 71); the "Existing precedents"
       bullet at lines 88-93 cites the forecasting lazy imports as "required because
       RunResponse.model_family computed_field closes the cycle at alembic cold-boot" — stale
       after this PRP; rewrite per Task 10.

- file: PRPs/PRP-reliability-E3-safe-uuid-non-secure-context.md
  why: House format for the reliability-epic PRP series (this file mirrors its structure).
```

### Current Codebase tree (relevant slice)

```bash
app/
├── core/logging.py                       # get_logger(name: str|None) -> FilteringBoundLogger
├── shared/
│   ├── __init__.py                       # exports ErrorResponse/Paginated*/TimestampMixin — DO NOT TOUCH
│   ├── feature_frames/                   # precedent: shared leaf package w/ own tests/
│   │   └── tests/__init__.py             # tests dirs have __init__.py in this repo
│   └── (no tests/ at shared top level — created by this PRP)
├── features/
│   ├── forecasting/
│   │   ├── __init__.py                   # EAGERLY imports service.py  ← arms the cycle
│   │   ├── schemas.py                    # :617-629 ModelFamily def (DELETE→move); :677 uses it
│   │   ├── feature_metadata.py           # :38-73 map+fn (DELETE→move); :30 imports from schemas
│   │   └── service.py                    # :55-61 NOTE; :967-968 S2; :1053-1054 S3
│   ├── registry/
│   │   ├── __init__.py                   # EAGERLY imports schemas+service  ← alembic entry
│   │   └── schemas.py                    # :20-27 eager import S1a; :175 lazy S1b
│   ├── model_selection/
│   │   ├── __init__.py                   # docstring-only (safe)
│   │   ├── capabilities.py               # :133-135 S4
│   │   └── service.py                    # :1077-1083 S5
│   ├── batch/service.py                  # :289-294 S6 (stale comment)
│   └── jobs/service.py                   # :435,:545 lazy ForecastingService — S3's counterpart, DO NOT TOUCH
└── alembic/env.py                        # :14-24 imports all models via packages → runs registry/__init__
```

### Desired Codebase tree

```bash
app/shared/model_taxonomy.py              # NEW — ModelFamily + _MODEL_FAMILY_MAP + model_family_for
app/shared/tests/__init__.py              # NEW — empty (repo convention)
app/shared/tests/test_model_taxonomy.py   # NEW — mapping + identity + schema-lock + cold-boot probes
app/features/forecasting/schemas.py       # MODIFIED — class deleted, re-export added
app/features/forecasting/feature_metadata.py  # MODIFIED — map+fn deleted, re-exports added
app/features/forecasting/service.py       # MODIFIED — S2 promoted, NOTE rewritten, S3 re-commented
app/features/registry/schemas.py          # MODIFIED — S1 shared imports, comment+docstrings updated
app/features/model_selection/capabilities.py  # MODIFIED — S4 promoted, docstring updated
app/features/model_selection/service.py   # MODIFIED — S5 promoted
app/features/batch/service.py             # MODIFIED — S6 promoted, stale docstring claim removed
docs/_base/ARCHITECTURE.md                # MODIFIED — precedents bullet rewritten
```

### Known Gotchas & Library Quirks

```python
# GOTCHA 1 — package __init__ eagerness is the trigger, not the leaf imports.
# registry/__init__.py imports schemas+service+storage; forecasting/__init__.py imports service;
# jobs/__init__.py imports routes+service. `from app.features.registry import models` therefore
# loads the ENTIRE registry slice. Never reason "alembic only imports models.py".

# GOTCHA 2 — pytest MASKS this cycle class. The conftest import order usually loads forecasting
# before registry, so an in-process test passes against broken code. Only a FRESH interpreter
# importing registry first (the alembic shape) reproduces. Hence the subprocess probes in the new
# suite AND the mandatory step-3.5 cold-boot smoke (uv run python -c "import app.main" +
# uv run alembic upgrade head) BEFORE Level-1 validation. Memory: [[computed-field-cross-slice-cycle]].

# GOTCHA 3 — mypy strict ⇒ no_implicit_reexport. A plain `from app.shared.model_taxonomy import
# ModelFamily` inside forecasting/schemas.py does NOT re-export it; registry tests importing
# ModelFamily from forecasting.schemas would fail mypy with attr-defined/no-redef noise.
# Use the redundant alias: `from app.shared.model_taxonomy import ModelFamily as ModelFamily`.
# ruff F401 also honors that idiom (no unused-import finding even when the name is otherwise
# unused, as in feature_metadata.py post-move); pylint's useless-import-alias is NOT enabled
# (ruff select has no PL group). If F401 fires anyway, fall back to `# noqa: F401` with a comment.

# GOTCHA 4 — Pydantic v2 needs ModelFamily at RUNTIME in registry/schemas.py even though the
# file has `from __future__ import annotations`: the computed_field return annotation is resolved
# when the serialization schema is built. Keep a module-scope runtime import (now from shared) —
# do NOT move it under TYPE_CHECKING.

# GOTCHA 5 — re-export must preserve OBJECT IDENTITY. forecasting.schemas.ModelFamily must BE
# app.shared.model_taxonomy.ModelFamily (same class object), or enum members would compare equal
# (str values) but `is` checks like `model_family_for(t) is ModelFamily.BASELINE`
# (forecasting/service.py:974) would silently break across paths. The new suite asserts identity.

# GOTCHA 6 — JSON schema is move-invariant. Verified 2026-06-11:
#   uv run python -c "
#   from app.features.registry.schemas import RunResponse
#   s = RunResponse.model_json_schema(mode='serialization')
#   print(s['$defs']['ModelFamily'])"
#   → {"enum": ["baseline", "tree", "additive"], "title": "ModelFamily", "type": "string", ...}
# Title comes from the class NAME, members from values — both unchanged. BUT the field
# `description` embeds the property docstring, so rewriting the lazy-import docstring changes the
# OpenAPI description text (cosmetic). Lock enum+title in the new suite; ignore description.

# GOTCHA 7 — ModelFamily is NOT pickled. Verified:
#   grep -rn "ModelFamily" app/features/forecasting/persistence.py   → no hits
# so old joblib bundles keep loading (pickle stores module paths — a pickled enum WOULD have
# broken). Re-verify with the same grep if persistence.py changed since 2026-06-11.

# GOTCHA 8 — keep the structlog event name "forecasting.unknown_model_family" verbatim in the
# moved function. It is a log contract (greppable); the module moved, the event didn't.
# Logger idiom in app/shared: `from app.core.logging import get_logger` then
# `logger = get_logger(__name__)` (precedent app/shared/seeder/core.py:15,48) — NOT the
# feature-module `structlog.get_logger` idiom.

# GOTCHA 9 — ruff S603 fires on subprocess in the new test. Use the house suppression
# (tests/test_e2e_demo.py:152): `subprocess.run(...)  # noqa: S603 — internal command, trusted args`
# and pass [sys.executable, "-c", stmt] (list form, no shell).

# GOTCHA 10 — isort (ruff I001) will want the promoted imports sorted inside the
# app-imports block. In forecasting/service.py the NOTE block (lines 55-61) currently sits in the
# MIDDLE of the import block (between schemas and v2_loaders) — when editing, move the rewritten
# NOTE to AFTER the import block ends (line ~80) or ruff format/I001 placement gets ugly.
# Run `uv run ruff check --fix . && uv run ruff format .` after each file edit.

# GOTCHA 11 — the cold-boot probes spawn fresh interpreters that import pandas/sklearn (~2-4 s
# each). Cap at 3 probes (alembic shape, forecasting-first, app.main) — ~10 s added to the unit
# suite. Do NOT parametrize over all 19 slices.

# GOTCHA 12 — repo has mixed CRLF/LF line endings with no policy. New files are fine (LF); for
# the 8 modified files check `git diff --stat` shows surgical hunks, not whole-file rewrites.

# GOTCHA 13 — the working tree may carry an unrelated dirty `uv.lock` and a local-only
# `docker-compose.lan.yml`. Do NOT sweep either into this branch.
```

## Implementation Blueprint

### Data models and structure

No ORM, no migration. One moved enum + map + function — complete spec:

```python
# app/shared/model_taxonomy.py — NEW (move, not rewrite; bodies verbatim from the old homes)
"""Model-family taxonomy shared across slices (#268).

``ModelFamily`` + ``model_family_for`` moved here from the forecasting slice
(``forecasting/schemas.py:617`` / ``forecasting/feature_metadata.py:38``):
``registry.schemas`` needs ``ModelFamily`` at module scope for the
``RunResponse.model_family`` computed field, and while the enum lived inside
a feature slice that one eager import forced lazy-import workarounds across
the registry boundary (the forecasting↔registry alembic cold-boot cycle).
A neutral ``app/shared`` home keeps the import graph one-way:
``app/features/* → app/shared`` only.
"""

from __future__ import annotations

from enum import Enum

from app.core.logging import get_logger

logger = get_logger(__name__)


class ModelFamily(str, Enum):
    """Classifier for advanced-model UI surfacing.

    Derived from ``model_type``; not persisted in the DB. Surfaced on
    ``RunResponse`` via a computed field and consumed by the dashboard for the
    family Badge and the feature-importance panel routing. Unknown model types
    classify as ``BASELINE`` (forward-compatible for new families before the
    map below is updated).
    """

    BASELINE = "baseline"  # naive, seasonal_naive, moving_average
    TREE = "tree"  # regression (HistGBR), lightgbm, xgboost
    ADDITIVE = "additive"  # prophet_like (Ridge pipeline)


# Canonical map: model_type string → ModelFamily. Unknown types log a warning
# and classify as BASELINE. Keep in sync with the ``ModelType`` Literal in
# ``app/features/forecasting/models.py``.
_MODEL_FAMILY_MAP: dict[str, ModelFamily] = {
    # ... the 11 entries VERBATIM from feature_metadata.py:42-54 ...
}


def model_family_for(model_type: str) -> ModelFamily:
    # ... body VERBATIM from feature_metadata.py:57-73, event name
    #     "forecasting.unknown_model_family" KEPT (Gotcha 8) ...
```

### Tasks (in order)

```yaml
Task 1:
CREATE app/shared/model_taxonomy.py:
  - CONTENT: exactly the spec above; map entries + function body moved VERBATIM from
    app/features/forecasting/feature_metadata.py:42-73; enum moved VERBATIM from
    app/features/forecasting/schemas.py:617-629 (docstring's "the map in feature_metadata.py"
    → "the map below")
  - Logger via app.core.logging.get_logger (Gotcha 8)

Task 2:
MODIFY app/features/forecasting/schemas.py:
  - DELETE lines 617-629 (class ModelFamily) and trim the section-header comment at 612-614 to
    "Feature Metadata Schemas (MLZOO-D / PRP-31; ModelFamily moved to app/shared/model_taxonomy — #268)"
  - ADD after the `from app.shared.feature_frames import FeatureGroup` import (line 18):
      # Back-compat re-export (#268): downstream modules and tests import ModelFamily from this
      # module; the redundant alias makes the re-export explicit for mypy/pyright/ruff.
      from app.shared.model_taxonomy import ModelFamily as ModelFamily
  - PRESERVE FeatureImportanceItem + FeatureMetadataResponse untouched (they stay here;
    FeatureMetadataResponse.model_family keeps the ModelFamily annotation, now via re-export)

Task 3:
MODIFY app/features/forecasting/feature_metadata.py:
  - DELETE lines 38-73 (_MODEL_FAMILY_MAP + model_family_for)
  - REPLACE line 30 `from app.features.forecasting.schemas import FeatureImportanceItem, ModelFamily`
    with:
      from app.features.forecasting.schemas import FeatureImportanceItem
      # Back-compat re-export (#268): forecasting/service.py and tests import these from here.
      from app.shared.model_taxonomy import ModelFamily as ModelFamily
      from app.shared.model_taxonomy import model_family_for as model_family_for
  - VERIFY nothing else in the file references _MODEL_FAMILY_MAP (it doesn't — verified)
  - Module docstring: no change needed (it describes importance extraction, which stays)

Task 4:
MODIFY app/features/registry/schemas.py:
  - REPLACE lines 20-27 (comment block + eager forecasting import) with:
      # ``ModelFamily`` / ``model_family_for`` live in ``app/shared/model_taxonomy`` (#268) so
      # this module never imports from another feature slice. Pydantic v2 resolves a
      # ``@computed_field``'s return-type annotation at schema-build time, so ``ModelFamily``
      # must be a real runtime import (never TYPE_CHECKING-gated).
      from app.shared.model_taxonomy import ModelFamily, model_family_for
  - SIMPLIFY the computed field (lines 166-177): delete the in-method import and the
    "Imported lazily…" docstring paragraph →
      @computed_field  # type: ignore[prop-decorator]
      @property
      def model_family(self) -> ModelFamily:
          """Computed family label derived from ``model_type``."""
          return model_family_for(self.model_type)
  - UPDATE RunResponse class docstring (lines 132-137): the canonical-map pointer
    "app/features/forecasting/feature_metadata.py:model_family_for" → "app/shared/model_taxonomy.py"

Task 5:
MODIFY app/features/forecasting/service.py:
  - ADD to the module import block (isort position — `registry` sorts AFTER `forecasting.*`,
    i.e. between the v2_loaders import and the app.shared.feature_frames import; let
    `uv run ruff check --fix .` settle the exact slot):
      from app.features.registry.schemas import RunStatus
      from app.features.registry.service import RegistryService
  - DELETE lines 966-968 (the "# Lazy cross-slice imports — see module-level NOTE." comment +
    both imports inside get_feature_metadata_for_run)
  - REWRITE the NOTE block (lines 55-61) and MOVE it below the import block (Gotcha 10):
      # NOTE: ``JobService`` and the job enums are imported LAZILY inside
      # ``get_feature_metadata_for_job``: ``jobs/service.py`` lazily imports
      # ``ForecastingService`` back at call time (lines ~435, ~545), so the pair is mutually
      # dependent and at least one side must stay call-time-lazy to keep cold-boot clean.
      # The registry imports above are EAGER since #268 moved ``ModelFamily`` to
      # ``app/shared/model_taxonomy`` — registry no longer imports this slice.
  - UPDATE the inline comment at line 1052 ("# Lazy cross-slice imports — see module-level NOTE.")
    → "# Lazy by design — see the jobs↔forecasting NOTE below the module imports."
  - PRESERVE everything else, incl. line 974 `model_family_for(run.model_type) is ModelFamily.BASELINE`
    (works unchanged via the existing module-scope imports from feature_metadata/schemas re-exports)

Task 6:
MODIFY app/features/model_selection/capabilities.py:
  - ADD module-scope import (sorted before the model_selection.schemas import):
      from app.shared.model_taxonomy import model_family_for
  - DELETE lines 133-135 (the lazy-import comment + import inside build_model_catalog)
  - UPDATE module docstring provenance bullet (lines 9-10):
      "- ``family`` — ``app.shared.model_taxonomy.model_family_for`` (shared taxonomy, #268)."

Task 7:
MODIFY app/features/model_selection/service.py:
  - ADD to the module import block (sorted after model_selection.* per isort… actually BEFORE —
    `registry` > `model_selection` alphabetically, so AFTER the model_selection imports):
      from app.features.registry.schemas import AliasCreate, RunCreate, RunStatus, RunUpdate
      from app.features.registry.service import RegistryService
  - DELETE lines 1077-1083 (both lazy imports + their `# lazy` comments inside
    promote_champion_selection)

Task 8:
MODIFY app/features/batch/service.py:
  - ADD to the module import block (sorted: data_platform < jobs, so after line 52):
      from app.features.jobs.models import JobStatus
      from app.features.jobs.schemas import JobCreate
      from app.features.jobs.service import JobService
  - DELETE lines 292-294 (the three lazy imports) and the docstring sentence at 289-290
    ("Lazy cross-slice imports break the alembic cold-boot cycle (precedent: …786-787).")
  - CHECK no name collisions: batch.models defines BatchStatus/BatchItemStatus, not JobStatus —
    verify with grep before promoting

Task 9:
CREATE app/shared/tests/__init__.py (empty) and app/shared/tests/test_model_taxonomy.py:
  - MIRROR style: app/features/forecasting/tests/test_feature_metadata.py:75-108
  - CASES:
      1. mapping: the 5 baseline types → BASELINE; regression/lightgbm/xgboost/random_forest →
         TREE; prophet_like/trend_regression_baseline → ADDITIVE  (canonical import path)
      2. unknown type → BASELINE fallback (no raise)
      3. IDENTITY (Gotcha 5):
           from app.shared.model_taxonomy import ModelFamily, model_family_for
           from app.features.forecasting.schemas import ModelFamily as SchemasMF
           from app.features.forecasting.feature_metadata import (
               ModelFamily as FMetaMF, model_family_for as legacy_fn)
           assert SchemasMF is ModelFamily and FMetaMF is ModelFamily
           assert legacy_fn is model_family_for
      4. JSON-schema lock (Gotcha 6):
           s = RunResponse.model_json_schema(mode="serialization")
           d = s["$defs"]["ModelFamily"]
           assert d["title"] == "ModelFamily" and d["enum"] == ["baseline", "tree", "additive"]
      5. cold-boot probes (Gotchas 1+2, the spec for the bug class), parametrized over EXACTLY:
           "from app.features.registry import models",      # alembic env.py shape
           "import app.features.forecasting",               # forecasting-first entry
           "import app.main",                                # full wiring
         each run as:
           result = subprocess.run(  # noqa: S603 — internal command, trusted args
               [sys.executable, "-c", stmt], capture_output=True, text=True, timeout=120)
           assert result.returncode == 0, result.stderr
  - DO NOT touch app/features/forecasting/tests/test_feature_metadata.py or
    app/features/registry/tests/test_schemas.py — green-untouched is the back-compat proof

Task 10:
MODIFY docs/_base/ARCHITECTURE.md (section "### Cross-slice read-only import pattern", line ~71):
  - REPLACE the "Existing precedents" forecasting bullet (lines ~91-93: "lazy RegistryService /
    JobService / RunStatus imports … required because RunResponse.model_family computed_field
    closes the cycle at alembic cold-boot") with:
      - `app/features/forecasting/service.py` ↔ `app/features/jobs/service.py` — mutually lazy
        service pair (each lazily imports the other at call time; at least one side must stay
        lazy). The former ModelFamily-driven cycle here was RESOLVED by #268.
  - ADD a short "Resolved cycle (reference case)" line after the precedents:
      - #268 moved `ModelFamily` + `model_family_for` to `app/shared/model_taxonomy.py`; the
        registry→forecasting eager edge disappeared and the registry-related lazy imports were
        promoted to module scope. When a cycle is caused by a shared *type*, relocate the type
        to `app/shared/` instead of adding lazy imports.

Task 11:
RUN the validation loop below (Level 0 cold-boot smoke FIRST — prp-execute step 3.5).
```

### Integration Points

```yaml
BACKEND:   8 files modified + 3 created — no router change, no schema change, no migration
DATABASE:  none (ModelFamily never persisted)
CONFIG:    none
DOCS:      docs/_base/ARCHITECTURE.md only (Task 10); API_CONTRACTS/DOMAIN_MODEL grep-verified clean
FRONTEND:  none (enum values + JSON-schema title unchanged)
GIT:
  branch:  refactor/shared-model-taxonomy        (off dev; type/kebab, ≤50 chars)
  commits: refactor(forecast,registry): move model family taxonomy to shared (#268)
           # the PRP file itself lands as:
           docs(repo): track reliability E4 prp for shared model taxonomy (#268)
           # (mirrors the E2/E3 "docs(repo): track reliability EN prp …" precedent)
  note:    refactor type → no version bump (correct; this is internal)
```

## Validation Loop

### Level 0: Cold-boot smoke (MANDATORY FIRST — prp-execute step 3.5; pytest masks this class)

```bash
uv run python -c "import app.main; print('app.main ok')"
uv run python -c "from app.features.registry import models; print('alembic-shape ok')"
uv run python -c "import app.features.forecasting; print('forecasting-first ok')"
docker compose up -d && uv run alembic upgrade head     # real env.py execution
# Baseline before edits (verified 2026-06-11): all four pass. They must STILL pass after.
```

### Level 1: Syntax & Style

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/        # strict; watch for no_implicit_reexport errors → Gotcha 3
uv run pyright app/     # strict; 197 pre-existing warnings are baseline noise, 0 errors is the bar
```

### Level 2: Unit Tests

```bash
# Targeted first (fast signal):
uv run pytest -v app/shared/tests/test_model_taxonomy.py \
    app/features/forecasting/tests/test_feature_metadata.py \
    app/features/registry/tests/test_schemas.py
# Then the full unit suite (baseline 2026-06-11: 1920 passed):
uv run pytest -v -m "not integration"
# Expected: old suites green UNTOUCHED; new suite adds ~10 cases incl. 3 subprocess probes (~10 s).
```

### Level 3: Integration (touched slices; DB must be up)

```bash
uv run pytest -v -m integration app/features/registry app/features/forecasting \
    app/features/model_selection app/features/batch
# Memory [[integration-suite-shared-state-pollution]]: do NOT run the FULL integration suite as
# the gate — destructive seeder tests pollute the shared DB mid-suite; targeted slices suffice.

# Live contract sanity (uvicorn running):
curl -s "http://localhost:8123/registry/runs?page=1&page_size=1" | python3 -c \
  "import sys,json; r=json.load(sys.stdin)['runs']; print('model_family:', r[0]['model_family'] if r else 'empty-table-ok')"
# Expected: one of baseline|tree|additive (or empty-table-ok on a fresh DB).
```

### Level 4: Full gates + issue sanity

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pyright app/ \
  && uv run pytest -v -m "not integration"
gh issue view 268 --json state          # OPEN until the PR lands
grep -rn "from app.features.forecasting" app/features/registry/   # MUST be empty
grep -rn "lazy" app/ --include="*.py" -i | grep -i "modelfamily\|model_family"   # MUST be empty
```

## Final Validation Checklist

- [ ] Level 0 cold-boot: all four probes pass AFTER the refactor (the alembic-shape one is the bug)
- [ ] `uv run pytest -v -m "not integration"` — green; both pre-existing suites UNTOUCHED
- [ ] New suite: mapping + identity (`is`) + JSON-schema lock + 3 subprocess probes green
- [ ] `grep -rn "from app.features.forecasting" app/features/registry/` → empty
- [ ] Zero comments blame the ModelFamily cycle for laziness (umbrella #380 acceptance)
- [ ] S3 kept lazy with the corrected jobs↔forecasting comment; `jobs/service.py:435,545` untouched
- [ ] `docs/_base/ARCHITECTURE.md` precedents bullet rewritten (Task 10)
- [ ] `git diff --stat` surgical (Gotcha 12); no `uv.lock` / `docker-compose.lan.yml` churn (Gotcha 13)
- [ ] Commits `refactor(forecast,registry): … (#268)`; no AI trailer; branch off `dev`

---

## Anti-Patterns to Avoid

- ❌ Don't REWRITE the enum/map/function while moving — move verbatim; behavior change is scope creep
- ❌ Don't gate the registry import under `TYPE_CHECKING` — Pydantic needs ModelFamily at runtime (Gotcha 4)
- ❌ Don't use a plain import as the re-export — mypy no_implicit_reexport breaks downstream (Gotcha 3)
- ❌ Don't eagerize `jobs/service.py:435,545` or forecasting's S3 to "finish the job" — that pair is
  a genuinely mutual dependency; both-eager = the cycle returns (S3 verdict)
- ❌ Don't add ModelFamily to `app/shared/__init__.py` — feature_frames precedent imports by full path
- ❌ Don't trust an in-process pytest pass as cycle proof — only fresh-interpreter probes count (Gotcha 2)
- ❌ Don't rename the `forecasting.unknown_model_family` log event (Gotcha 8)
- ❌ Don't touch `app/features/data_platform` cross-slice imports — separately tracked sibling flag

## Confidence Score: 9/10

One-pass success is highly likely: the cycle topology is fully traced and runtime-verified (all
entry orders), every mutation site is mapped with verbatim current text and a per-site verdict,
the re-export idiom is checked against the actual mypy/ruff config, and the regression suite
includes the one test shape (fresh-interpreter probes) that this bug class cannot hide from.
The 1-point deduction: isort/ruff-format placement of the promoted imports and the relocated
NOTE block in `forecasting/service.py` (Gotcha 10) may need one fix-up iteration, and the
subprocess probes' wall-clock cost could need trimming if the unit-suite budget complains.
