# Artifacts and the registry

How a trained model becomes a verifiable, promotable thing — and what the system refuses to do when it cannot verify one.

**Purpose:** understand run lifecycle, artifact integrity, and alias semantics well enough to build on them.
**Intended reader:** integrators consuming registry data or automating promotion.

## What you'll accomplish

The ability to trace any served prediction back to a specific run, its configuration, its data window, and a checksum that proves the artifact has not changed.

## Why a registry exists

A trained model is useless as evidence unless you can say *which* model it was. Without a registry you get a directory of pickle files and an argument about which one is in production.

A `model_run` row answers: what model type, at what grain, over which data window, with which configuration and seed, scoring what, backed by which artifact — and whether that artifact still hashes to what it did when it was written.

## The run lifecycle

```
pending  →  running  →  success
                     ↘  failed
```

| Endpoint | Purpose |
|---|---|
| `POST /registry/runs` | Create a run record — starts `pending`. |
| `GET /registry/runs` | List with filters, pagination, sorting. |
| `GET /registry/runs/{run_id}` | Details, metrics, runtime info. |
| `PATCH /registry/runs/{run_id}` | Update status, metrics, or artifact location. |
| `GET /registry/runs/{run_id}/verify` | **Verify artifact SHA-256.** |
| `GET /registry/compare/{a}/{b}` | Diff two runs. |

Only a **successful** run may be aliased. A `failed` run keeps its record — a failure is data about what does not work, and deleting it would let the same experiment be repeated blindly.

## Artifact integrity

When a model is fitted, the artifact is written to disk and its **SHA-256** recorded on the run.

`GET /registry/runs/{run_id}/verify` re-computes the hash and compares. Three outcomes matter:

- **Verified** — the file on disk is byte-identical to what was recorded.
- **Mismatch** — the file changed. Whatever it is now, it is not what was measured.
- **Missing** — the file is gone.

The last two are indistinguishable in consequence: the run's metrics describe a model you can no longer produce.

### This is the one gate with no override

The Promote dialog auto-fetches the verification result. **A failure disables the Promote button with no operator override** — unlike the worse-WAPE and feature-frame-mismatch gates, which are acknowledgeable checkboxes.

The asymmetry is deliberate. "This model scores worse and I accept that" is a judgement a human can make. "This file is not the model I measured" is not a judgement at all — there is nothing to weigh. Re-train to produce a verifiable artifact.

Artifact roots are configurable: `forecast_model_artifacts_dir`, `backtest_results_dir`, `registry_artifact_root`, and `showcase_export_root` — all under `./artifacts/` by default, and inside the `forecastlab_artifacts` named volume in container mode.

**Deleting an artifact does not delete its run.** You get a row whose metrics still render, whose verification now fails, and whose feature-importance endpoint returns `422`. Archive runs through the registry rather than deleting files underneath it.

## Aliases

An alias is a movable, human-friendly pointer to one successful run.

| Endpoint | Purpose |
|---|---|
| `POST /registry/aliases` | Create or move an alias. |
| `GET /registry/aliases` | List. |
| `GET /registry/aliases/{name}` | Fetch one. |
| `DELETE /registry/aliases/{name}` | Delete. |

Names must match `^[a-z0-9][a-z0-9\-_]*$`. Re-pointing an existing name is an **upsert**, not an error — that is how promotion works.

Aliases exist so a consumer can depend on `production` rather than a run id that changes every retrain. The indirection is the point: the consumer's contract stays stable while the model behind it moves.

## Promotion is a recorded decision

`POST /model-selection/{id}/promote` registers the trained model as a `model_run` transitioned to SUCCESS with a verified artifact, points an alias at it, and writes a `promotion_decision` audit: approver, alias, run id, decision, reason, and whether it overrode the recommendation.

Four preconditions, each its own `422`:

| Requirement | Rationale |
|---|---|
| Valid alias name | Aliases are addressable identifiers. |
| `approved_by` present | **Promotion is never anonymous.** |
| `acknowledge_non_recommended=true` for an override | Deliberate, not accidental. |
| The model is trained | You cannot promote what does not exist. |

**Compare and promote are separate operations.** Promote performs no ranking — it registers and aliases an already-trained model. Keeping them apart is what makes the audit meaningful: the comparison is *evidence*, the promotion is a *decision*, and they are recorded as different things by different actors.

Full workflow in [Champion selector](../analyst/champion-selector.md).

## Comparability

Two runs are comparable **if and only if**:

1. Same grain (`store_id`, `product_id`).
2. Overlapping data windows.
3. Same `feature_frame_version` — absent on older runs, which default to V1.

`GET /registry/compare/{a}/{b}` returns the diff, and the dashboard renders a **Champion compatibility** badge with the verdict plus a feature-frame-version row.

If you automate promotion, check this verdict rather than comparing metrics directly. Two WAPE numbers from different grains are two answers to different questions, and nothing in the numbers themselves will tell you that.

## Staleness

`GET /ops/model-health` surfaces stale aliases with a reason:

| Reason | Meaning | Urgency |
|---|---|---|
| `newer success run` | A newer successful run exists at this grain. | Routine. |
| `artifact not verified` | The alias's artifact failed verification. | **Urgent.** |
| `run not success` | The alias points at a failed or archived run. | High. |
| `V mismatch` | The newest comparable run uses a different `feature_frame_version`. | Subtle. |

`V mismatch` is the one that does not announce itself. Nothing errors when the feature contract drifts — a downstream pipeline keeps running while supplying columns the new version does not expect, or omitting ones it does. It degrades quietly, which is why crossing that boundary requires an explicit acknowledgement at promotion time.

## Duplicate policy

`registry_duplicate_policy` (default `detect`):

- `detect` — flag but allow.
- `deny` — reject.
- `allow` — record silently.

`detect` surfaces accidental repeat work without blocking a deliberate re-run.

## Building on the registry

**Resolve through aliases, not run ids**, so retraining does not require a consumer change.

**Verify before serving.** `GET /registry/runs/{run_id}/verify` is cheap next to serving predictions from an artifact that is not what you measured.

**Treat `feature_frame_version` as part of the contract.** If you feed a promoted model, a version change means your input columns must change too.

**Never write registry rows directly.** A hand-written row bypasses artifact bookkeeping — its metrics will display and its promotion will fail. See [Data model](data-model.md#querying-directly).

## Next

- [Extending ForecastLabAI](extending.md) — adding models and slices without breaking these guarantees.
- [CI and quality gates](ci-and-quality-gates.md) — what enforces all of this.
