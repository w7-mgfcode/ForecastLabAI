# PRP-14: Schema-Policy Invariant Linter

**Phase**: 14
**Status**: Ready for Implementation
**PRP Score**: 9/10 (High confidence for one-pass implementation — scope confirmed by grep; zero new deps)
**Estimated Complexity**: Low (one ~80-LOC test file + one-line doc cross-ref)

> **Owner:** Maintainer (Gabor Szabo)
> **Promoted from:** `PRD.md` (2026-05-14) — synthesized from the 2026-05-13 brainstorm session anchored against PR #115 (issue #109) and PR #119 (issue #117) regression evidence.

---

## 1. Executive Summary

Pydantic v2's `ConfigDict(strict=True)` combined with FastAPI's `validate_python` path causes every JSON-string value for a JSON-non-native type (`date`, `datetime`, `time`, `UUID`, `Decimal`) to fail with a 422 `*_type` error. The repo has already shipped this bug twice in fourteen days — `ComputeFeaturesRequest.cutoff_date` (PR #115, closing #109) and `TrainRequest.train_start_date`/`train_end_date` (PR #119, closing #117). Each time the fix was the same one-line `Field(strict=False, ...)` override; each time the policy was only enforced by a human reviewer reading `docs/_base/SECURITY.md`.

This PRD specifies a **policy-as-test** module — `app/core/tests/test_strict_mode_policy.py` — that walks every Pydantic request model under `app/features/**/schemas.py`, identifies the `ConfigDict(strict=True)` + JSON-non-native-field combination, and fails the build when an offending field is missing its `Field(strict=False, ...)` annotation. The test is modeled on the existing load-bearing `test_leakage.py` precedent: a one-file, zero-dependency invariant that the rest of the codebase is measured against.

**MVP goal:** ship a passing pytest module that catches the next instance of this regression class before it leaves a contributor's machine — without changing any runtime behavior or adding any production dependency.

## 2. Mission

Codify the Pydantic-v2 strict-mode policy that landed in `docs/_base/SECURITY.md` as an executable, never-weaken invariant — so the strict-typing identity that CLAUDE.md and `.claude/rules/security-patterns.md` claim is automatically enforced at the same point of trust as `mypy --strict` and `pyright --strict`.

**Core principles**

1. **Policy is executable, not prose.** If a rule matters enough to document, it matters enough to test.
2. **Reviewer-enforced rules will be forgotten.** Frequency-2 in 14 days is the empirical proof.
3. **Zero new dependencies.** Use stdlib `ast` against the schemas tree; do not import the models at runtime.
4. **Mirror the `test_leakage.py` precedent.** One file, opinionated fixture set, clear failure messages, cited in CLAUDE.md / RULES.md as a never-weaken spec.
5. **Additive, not breaking.** Existing 4 known-good models must pass on day one; the linter never *demands* a refactor — it only blocks new violations.

## 3. Target Users

| Persona | Technical comfort | Primary needs | Pain today |
|---------|-------------------|---------------|------------|
| **Maintainer (Gabor)** | Senior Python / FastAPI | Trust that the strict-typing identity holds across the 11 slices without per-PR vigilance | Hit the same bug twice in two weeks; each fix is mechanical but the discovery cost was non-trivial |
| **Future contributor adding a slice** | Mid → senior Python | Land a new `routes.py` + `schemas.py` without rediscovering the JSON-validate-python interaction | No automated signal that `ConfigDict(strict=True)` + a `date` field is unsafe; `mypy --strict` cannot see it |
| **Claude as code-generator** | n/a | A test failure is the most reliable correction signal in the loop | Currently the agent has to read `docs/_base/SECURITY.md` to know the rule exists |

## 4. MVP Scope

### In Scope

**Core functionality**
- ✅ `app/core/tests/test_strict_mode_policy.py` — single pytest module, `ast`-based walker
- ✅ Scan target: `app/features/**/schemas.py` only (not `models.py`, not response schemas — see Decisions / Open Questions)
- ✅ Detect classes whose body contains `model_config = ConfigDict(strict=True)` (also handle `ConfigDict(... strict=True ...)` with other kwargs)
- ✅ For each such class, identify fields annotated with any of: `date`, `datetime`, `time`, `UUID`, `Decimal` (including `Optional[T]`, `T | None`, `Annotated[T, ...]`, `list[T]`, `dict[K, T]`)
- ✅ For each detected field, require its default to be `Field(strict=False, ...)` — fail otherwise with a row showing `<file>:<line> <Model>.<field> typed <T> needs Field(strict=False, ...)`
- ✅ A self-contained **negative-fixture** sub-test that synthesizes an offending model and asserts the walker reports it (proves the linter actually works)
- ✅ Cross-reference in `docs/_base/SECURITY.md` "Pydantic v2 strict mode on FastAPI request bodies" — add a one-line "**Enforced by:** `app/core/tests/test_strict_mode_policy.py`"

**Technical**
- ✅ Pure stdlib `ast` — no importing model classes at test time (avoids circular-import surprises, speeds the test, and isolates the linter from runtime side effects)
- ✅ Resolves type aliases imported as `from datetime import date` and `import datetime as dt` (the two idioms used in the existing tree)
- ✅ Runs under `pytest -m "not integration"` — fast unit pass
- ✅ Passes `mypy --strict` + `pyright --strict` cleanly

**Integration**
- ✅ Wired into the existing CI `Test` job (no new workflow needed — the test is picked up by the existing `pytest -v -m "not integration"` invocation)

**Deployment**
- ✅ No deployment surface — test-only change

### Out of Scope

- ❌ Response models (`*Response`, `*Item`) — the regression class only affects request bodies
- ❌ `app/shared/seeder/config.py` Pydantic models — they aren't FastAPI request bodies (CLI / in-code construction only). Tracked as Open Question.
- ❌ `app/features/agents/tools/*` tool-arg schemas — PydanticAI validates differently; revisit if the same regression hits there
- ❌ Auto-fix mode (the test surfaces, does not patch)
- ❌ A pre-commit hook variant (the CI `Test` job is sufficient; pre-commit adds setup friction)
- ❌ Plugin / custom Pydantic validator architecture
- ❌ Backporting `Field(strict=False, ...)` to any model that doesn't currently have a date/UUID/Decimal field (no preemptive churn)

## 5. User Stories

**US-1 — Maintainer pattern guard**
> *As the* maintainer*, I want* the next PR that re-introduces the JSON-strict-mode bug to fail CI on `Test` *so that* the regression cannot land for a third time.
> *Example:* Contributor adds `class UpdateRunRequest(BaseModel)` with `ConfigDict(strict=True)` and `archive_at: datetime`. CI fails:
> ```
> FAILED app/core/tests/test_strict_mode_policy.py::test_strict_request_models_field_safe
> app/features/registry/schemas.py:142  UpdateRunRequest.archive_at  typed datetime  needs Field(strict=False, ...)
>   See docs/_base/SECURITY.md → "Pydantic v2 strict mode on FastAPI request bodies"
> ```

**US-2 — New-slice author safety**
> *As a* contributor adding `app/features/<new_slice>/schemas.py`*, I want* an immediate, local pytest signal *so that* I learn the rule once and never re-trip it.

**US-3 — Claude-loop correction**
> *As* Claude operating in `do:implementation` / `do:review` skills*, I want* the linter to surface the failure in the standard `Test` job output *so that* I can self-correct without needing the operator to paste in `docs/_base/SECURITY.md`.

**US-4 — Reviewer time saved**
> *As a* reviewer on a Pydantic-touching PR*, I want* to not have to remember to grep for `ConfigDict(strict=True)` next to date fields *so that* my review effort moves to the actual business logic.

**US-5 — Policy traceability**
> *As a* future maintainer reading `docs/_base/SECURITY.md`*, I want* the policy paragraph to cite its enforcement test *so that* I can answer "is this still enforced?" in 5 seconds.

**US-6 — Negative-fixture confidence**
> *As the* author of the linter*, I want* a self-test that the walker actually catches an offending model *so that* the green pytest output is meaningful (not vacuous).

**US-7 — Zero-disruption landing**
> *As the* maintainer*, I want* the linter to pass on the existing 4 known-good models on commit one *so that* the landing PR is a pure-test add with no schema churn in the diff.

## 6. Core Architecture & Patterns

**Approach.** AST-walk based, not runtime-import based. The test opens each `schemas.py` file under `app/features/`, parses with `ast.parse`, walks `ClassDef` nodes that subclass `BaseModel` (directly or transitively-visible inside the file's imports), inspects each class body for the `model_config = ConfigDict(...)` assignment, extracts the `strict` kwarg, then walks `AnnAssign` field declarations to flag the targeted type names.

**Why AST over runtime import.** Runtime import of every `schemas.py` causes:
1. Side effects on SQLAlchemy model registration (slow).
2. Coupling between this test and every slice's import graph.
3. Failure modes if a slice's `schemas.py` raises at import time during development.
AST is read-only, fast, and isolates the test from runtime state.

**Directory placement**

```
app/
├── core/
│   └── tests/
│       ├── conftest.py                        # existing
│       ├── test_config.py                     # existing
│       ├── test_health.py                     # existing
│       ├── test_logging.py                    # existing
│       ├── test_middleware.py                 # existing
│       └── test_strict_mode_policy.py         # NEW — ~80 LOC
```

**Why `app/core/tests/`** — the policy is cross-slice; it doesn't belong in any one feature's tree. `app/core/tests/` already houses cross-cutting tests (config, middleware, logging).

**Key design patterns**

| Pattern | Source precedent | Reuse here |
|---------|-----------------|------------|
| Load-bearing invariant test | `app/features/featuresets/tests/test_leakage.py` | Same idiom: one file, opinionated, cited in CLAUDE.md / RULES.md |
| Self-test via embedded fixture | Various `conftest.py` patterns | Use `ast.parse(textwrap.dedent("..."))` on a synthetic offending model |
| Pytest parametrize over discovered targets | `app/features/featuresets/tests/test_schemas.py` | `@pytest.mark.parametrize` over the discovered `(file, model, field)` tuples for clearer failure output |

**Failure-output contract**

```
========================== short test summary info ==========================
FAILED app/core/tests/test_strict_mode_policy.py::test_strict_request_models_field_safe[registry/schemas.py::UpdateRunRequest::archive_at]
AssertionError:
  app/features/registry/schemas.py:142  UpdateRunRequest.archive_at  typed datetime  needs Field(strict=False, ...)
  See docs/_base/SECURITY.md → "Pydantic v2 strict mode on FastAPI request bodies"
  Fix pattern (mirrors PR #115 / PR #119):
      archive_at: datetime = Field(strict=False, description="...")
```

## 7. Features / Tools

**F-1 — `iter_strict_request_models(features_root: Path) -> Iterator[StrictModelHit]`**
- Walks `app/features/*/schemas.py`
- Parses with `ast`; yields each `ClassDef` that has `model_config = ConfigDict(... strict=True ...)`
- Returns `StrictModelHit(file: Path, lineno: int, model_name: str, class_node: ast.ClassDef, type_aliases: dict[str, str])`

**F-2 — `iter_json_non_native_fields(hit: StrictModelHit) -> Iterator[FieldHit]`**
- For each `AnnAssign` in the class body, resolves the annotation against `type_aliases` (handles `Optional[T]`, `T | None`, `Annotated[T, ...]`)
- Yields `FieldHit(name, lineno, resolved_type_name)` for each field typed `date | datetime | time | UUID | Decimal`

**F-3 — `field_has_strict_false_override(field_hit: FieldHit) -> bool`**
- Inspects the `AnnAssign.value` (the field default)
- Returns `True` iff the default is a `Call` to `Field` with a `strict=False` keyword

**F-4 — `test_strict_request_models_field_safe`** (the actual pytest)
- Parametrized over the cartesian of F-1 × F-2 hits
- Asserts F-3 holds for each
- Failure message is the contract from §6 above

**F-5 — `test_linter_catches_synthetic_violation`** (negative fixture)
- Constructs a synthetic offending model in-source via `textwrap.dedent` + `ast.parse`
- Runs F-1, F-2, F-3 against it; asserts the walker reports the synthetic field
- Proves the green output of F-4 is not vacuous

## 8. Technology Stack

| Layer | Choice | Version | Status |
|-------|--------|---------|--------|
| Language | Python (already pinned at repo level) | 3.12 | reuse |
| Test framework | pytest (already in dev deps) | ≥8 | reuse |
| AST parser | stdlib `ast` | — | stdlib |
| Path traversal | stdlib `pathlib.Path.glob` | — | stdlib (rule `PTH` aligned) |
| Type-hint helpers | stdlib `typing` (no `typing_extensions` required) | — | stdlib |
| Type checker | `mypy --strict` + `pyright --strict` | already in CI | reuse |
| Linter | `ruff check` + `ruff format --check` | already in CI | reuse |

**No new dependencies.** Anything added to `pyproject.toml` would itself need an issue per `.claude/rules/security-patterns.md` (third-party additions get scrutiny).

## 9. Security & Configuration

**Authentication / authorization** — N/A (test-only change).

**Configuration**
- No new env vars
- No new settings in `app/core/config.py`
- Test discovers `app/features/` relative to the test file's location (`Path(__file__).resolve().parents[2] / "features"`)

**Security scope**

| In scope | Out of scope |
|----------|--------------|
| Closing a recurring information-disclosure-adjacent regression (422 leak path is itself fine, but the bug class undermines the "Pydantic v2 at every boundary" identity claim in `docs/_base/SECURITY.md`) | Adding any security scanner; touching `cd-release.yml`; modifying secret-handling |
| Codifying one bullet from `docs/_base/SECURITY.md` "Pydantic v2 strict mode on FastAPI request bodies" subsection | Codifying other security-patterns.md bullets (deferred to follow-up issues if useful) |

**Deployment** — none. The change ships when the PR merges to `dev`, runs in CI from the next commit.

## 10. API Specification

N/A. This feature has no HTTP, WebSocket, CLI, or agent-tool surface. The only public artifact is the failing pytest output (contract documented in §6 "Failure-output contract").

## 11. Success Criteria

### MVP success definition

The next PR that adds a `ConfigDict(strict=True)` request model with a `date | datetime | time | UUID | Decimal` field — without the `Field(strict=False, ...)` override — fails `pytest -m "not integration"` locally and the `Test` CI job, with a row-by-row report pointing the contributor at `docs/_base/SECURITY.md`.

### Functional requirements

- ✅ The 4 already-known-good models pass on commit one (no schema churn in the landing PR diff)
- ✅ A synthetic offending model in the negative-fixture test is reported correctly (proves the walker)
- ✅ All `app/features/*/schemas.py` files are walked. The 2 slices currently containing the 4 known-good models (`featuresets`: `ComputeFeaturesRequest`, `PreviewFeaturesRequest`; `forecasting`: `TrainRequest`, `PredictRequest`) all PASS on commit one. The other 10 slices are scanned defensively — they have zero `ConfigDict(strict=True)` today, but the walker future-proofs them: any slice that flips on strict-mode without matching `Field(strict=False, ...)` on a `Decimal`/`date`/`datetime`/`time`/`UUID` field is caught immediately. (`Decimal` request fields already exist in `analytics`, `data_platform`, `dimensions`, `ingest` — the bomb is loaded; this linter is the safety pin.)
- ✅ `pytest -v -m "not integration"` runtime grows by < 200 ms (AST parsing is fast; if it doesn't, the implementation is wrong)
- ✅ `mypy --strict app/` and `pyright --strict app/` both clean on the new file
- ✅ `ruff check` and `ruff format --check` clean on the new file
- ✅ `docs/_base/SECURITY.md` "Pydantic v2 strict mode on FastAPI request bodies" subsection ends with `**Enforced by:** \`app/core/tests/test_strict_mode_policy.py\``

### Quality indicators

| Indicator | Target |
|-----------|--------|
| Failure message includes file, line, model, field, type, fix-pattern, doc pointer | All five elements present |
| Negative fixture exercises an `Optional[date]`, `datetime`, and `UUID` case | At least one of each |
| Test count added to baseline `pytest` run | 1 parametrized test (currently 4 cases) + 1 negative-fixture test |
| Citation in `CLAUDE.md` (under "Safety" or "Verification") | Optional polish; not required for MVP |

### User experience

A contributor with no prior context who introduces the bug class sees a single, actionable failure row, fixes it with a one-line change matching the documented pattern, and re-runs. Total recovery loop: < 60 seconds.

## 12. Implementation Phases

### Phase 1 — Walker scaffold (Day 1, ~2 hours)
**Goal.** Produce the `ast`-based walker that finds `ConfigDict(strict=True)` model classes across `app/features/*/schemas.py`.
**Deliverables.**
- ✅ `app/core/tests/test_strict_mode_policy.py` skeleton with F-1 `iter_strict_request_models` implementation
- ✅ Smoke-asserts: walker finds exactly the 2 known classes (`ComputeFeaturesRequest`, `PreviewFeaturesRequest`, `TrainRequest`, `PredictRequest`)
**Validation.** Run the test locally; print discovered model names. Confirm expected set. No CI run yet.

### Phase 2 — Field detection + override check (Day 1, ~2 hours)
**Goal.** F-2 `iter_json_non_native_fields` + F-3 `field_has_strict_false_override` + the parametrized `test_strict_request_models_field_safe`.
**Deliverables.**
- ✅ Resolution logic for `Optional[T]`, `T | None`, `Annotated[T, ...]`, `list[T]`, `dict[K, T]`
- ✅ Resolution for `date`/`datetime`/`time`/`UUID`/`Decimal` regardless of import alias
- ✅ Pytest passes against the existing tree (proof the codebase is in compliance today)
**Validation.** `uv run pytest app/core/tests/test_strict_mode_policy.py -v` → green, exactly 3 parametrized cases (cutoff_date, train_start_date, train_end_date) reported as PASSED.

### Phase 3 — Negative-fixture self-test + doc cross-ref (Day 2, ~1 hour)
**Goal.** F-5 negative fixture + `docs/_base/SECURITY.md` pointer.
**Deliverables.**
- ✅ `test_linter_catches_synthetic_violation` covering at least one of each: `Optional[date]`, `datetime`, `UUID`
- ✅ `docs/_base/SECURITY.md` updated with the "Enforced by" pointer (one line, ≤ 80 chars)
**Validation.** `pytest -v` → 1 parametrized passing + 1 negative passing. Full gate: `ruff check . && uv run mypy app/ && uv run pyright app/ && pytest -m "not integration"` clean.

### Phase 4 — Branch, PR, land (Day 2, ~1 hour)
**Goal.** Ship.
**Deliverables.**
- ✅ Open follow-up GitHub issue referencing #117 ("codify strict-mode policy as test")
- ✅ Branch `feat/api-strict-mode-policy-linter` off `dev` per `.claude/rules/branch-naming.md`
- ✅ Single commit `feat(api): codify pydantic strict-mode policy as pytest invariant (#<N>)` per `.claude/rules/commit-format.md` (no AI co-author trailer)
- ✅ PR into `dev` with body citing PR #115 and PR #119 as precedent
- ✅ All 5 blocking CI jobs (Lint & Format, Type Check, Test, Migration Check, plus Socket / CodeRabbit informational) green
**Validation.** Reviewer merges into `dev` via GitHub web UI; CI on `dev` green post-merge.

**Total estimated effort:** 4–6 focused hours, ~1.5 working days end-to-end.

## 13. Future Considerations

**Adjacent enforcers (each its own issue, not part of this PRD)**
- Walker extension to `app/features/agents/tools/*` arg schemas if PydanticAI is ever found to share the regression class.
- Walker extension to `app/shared/seeder/config.py` Pydantic models (currently out of scope — they aren't HTTP request bodies, but the regression class would still surprise a contributor calling `model_validate(dict)`).
- A second invariant test: "every route handler accepting `application/json` has a Pydantic request model" — different rule, same precedent.
- A third invariant test: "every public route returns `RFC 7807 problem+json` on error paths" — same precedent.

**Tooling polish (post-MVP)**
- A `pytest --tb=line` mode that prints only the per-row offense lines without traceback — better signal in CI log output.
- A `ruff` custom rule or a `flake8`-plugin variant — currently rejected because both would be new dependencies; revisit only if the test approach proves slow.

**Documentation**
- A `.claude/rules/strict-mode-policy.md` rule file if `.claude/` ever stops being gitignored (see brainstorm Open Question #3).

## 14. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------:|-------:|------------|
| **Type-annotation resolver misses an idiom** (e.g., `Annotated[Optional[date], Field(...)]` nested form) | Med | Med — false-negative lets a bug slip | Add fixture rows for every known idiom variant the codebase actually uses; if unknown idiom encountered at scan time, fail the test with "unrecognized annotation form, extend resolver" rather than silent-pass |
| **AST walker false-positive on a non-FastAPI Pydantic model under `app/features/*/schemas.py`** | Low | Low — flags a model that doesn't actually go through FastAPI | Scope is *all* request-shaped schemas; the cost of a false-positive is a one-line `Field(strict=False, ...)` add that's harmless at runtime. Document the scope explicitly |
| **`docs/_base/SECURITY.md` policy text drifts from the linter** | Low | Med — confuses contributors about what's enforced | Cross-reference in both directions: doc cites the test, test docstring cites the doc |
| **The single test grows into a sprawling lint framework over time** | Low | Med — scope creep | This PRD's §12 caps it at one file, ~80 LOC, two test functions. Anything beyond F-1..F-5 is a new PRD |
| **PR title hits the release-please merge-subject trap when landing on `dev`** | Low | Low — `dev` merges don't trigger release | Use `feat(api): ...` prefix per `.claude/rules/commit-format.md`; `dev`→`main` merge is a separate later step covered by `docs/_base/RUNBOOKS.md` |

## 15. Appendix

### Related repository artifacts

- **Precedent invariant test.** `app/features/featuresets/tests/test_leakage.py` — load-bearing "policy as test" cited in CLAUDE.md / RULES.md
- **Policy text.** `docs/_base/SECURITY.md` → "Pydantic v2 strict mode on FastAPI request bodies" subsection (added by PR #115)
- **Bug class history.**
  - PR #115 (closes issue #109): `ComputeFeaturesRequest.cutoff_date`, `PreviewFeaturesRequest.cutoff_date`
  - PR #119 (closes issue #117): `TrainRequest.train_start_date`, `TrainRequest.train_end_date`
- **Rule files.** `.claude/rules/security-patterns.md` — same policy text mirrored locally (note: `.claude/` is currently gitignored — see brainstorm Open Question #3)
- **Commit-format / branch-naming rules.** `.claude/rules/commit-format.md`, `.claude/rules/branch-naming.md`
- **Runbook referenced for landing.** `docs/_base/RUNBOOKS.md` → "release-please skipped the bump after a dev → main merge" (relevant only if/when this work is included in a `dev`→`main` release PR)

### Key dependencies

| Dependency | Purpose | Version | Source |
|------------|---------|---------|--------|
| `pydantic` | The runtime under test | ≥2 | `pyproject.toml` (already pinned) |
| `pytest` | Test runner | ≥8 | `pyproject.toml` (dev extra, already pinned) |
| stdlib `ast` | Source-level walker | 3.12 | stdlib |

### File touch list (estimate)

```
NEW   app/core/tests/test_strict_mode_policy.py        ~80 LOC
M     docs/_base/SECURITY.md                           +1 line
```

### Assumptions made (during PRD drafting)

1. **Scope is `app/features/*/schemas.py` only.** Tracked as Open Question #1 from the brainstorm — confirm before Phase 2 implementation begins.
2. **A new GitHub issue is acceptable** (rather than folding into the still-open #117). Tracked as Open Question #2.
3. **No additional JSON-non-native types** beyond `date | datetime | time | UUID | Decimal` need pre-emptive coverage. Tracked as Open Question #3.
4. **Estimated effort 4–6 hours** assumes an experienced Python author working uninterrupted; first-time-with-`ast` contributors could budget 8–10 hours.
5. **The linter ships as a pure-test addition** with zero schema-side changes in the diff (per US-7) — confirmed feasible by the brainstorm's "the existing 4 known-good models all pass on day one" assertion.

### Open questions — resolved on PRD acceptance (2026-05-14)

1. ✅ **Resolved — `app/features/**/schemas.py` only.** Grep confirmed `app/shared/seeder/config.py` has no `ConfigDict(strict=True)` and `app/features/agents/tools/*` has no `BaseModel` at all (PydanticAI `@agent.tool` decorators, not request bodies). Both stay out of scope; revisit if either subsystem ever adopts strict-mode request schemas.
2. ⏳ **Pending maintainer call.** Open a new GitHub issue tied to this PRP, or extend issue #117? Default if unclear at branching time: open a new issue (cleaner traceability against the linter PR).
3. ✅ **Resolved — no.** Grep of `app/features/*/schemas.py` shows zero usage of `ipaddress.*`, `pathlib.Path`, or `NewType` as field types. Ship the linter with `date | datetime | time | UUID | Decimal` and add types only when an actual codebase user appears.

---

### Next steps after PRD acceptance

1. Promote this file to `PRPs/PRP-14-strict-mode-policy-linter.md` (matches repo convention).
2. Open the tracking issue (resolves Open Question #2).
3. Branch `feat/api-strict-mode-policy-linter` off `dev`; execute Phase 1.
