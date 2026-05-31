# Showcase Manual Demo Guide

This guide describes how to manually review the ForecastLabAI `/showcase`
experience from a clean or controlled local environment. It is intended for
technical reviewers, maintainers, and users evaluating the product. It focuses
on what a person should see in the browser, what the system is doing behind
each phase, and how to interpret expected skips, warnings, and known
limitations.

For a shorter product walkthrough, see
[Showcase walkthrough](./showcase-walkthrough.md). For operational failure
diagnosis, see the showcase entries in
[Runbooks](../_base/RUNBOOKS.md).

## Audience and outcome

Use this guide when you want to answer three questions:

1. Can a visitor run the end-to-end retail forecasting demo from the browser?
2. Does the demo create the expected data, model, registry, batch, scenario,
   RAG, agent, and ops artifacts?
3. Are the reviewer-facing links and UI surfaces usable after the run?

The manual run is not a replacement for CI. It validates the product
experience that automated tests cannot fully cover: phase progression,
human-in-the-loop controls, post-run inspection, and explanatory UI.

## Prerequisites

Run the local stack:

```bash
docker compose up -d
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8123
```

In another terminal:

```bash
cd frontend
pnpm dev
```

Open:

```text
http://localhost:5173/showcase
```

The browser must be able to reach the backend. In `frontend/.env`, use:

```bash
VITE_API_BASE_URL=http://localhost:8123
```

Optional providers:

- An LLM API key that matches `agent_default_model` enables the agent HITL
  portion of the demo.
- A reachable embedding provider enables the RAG indexing and retrieve
  portions. Without one, the knowledge steps should skip gracefully.

## Safety note about database reset

The **Reset database** checkbox is destructive. It is useful for a true
fresh-DB demo, but it wipes local data before reseeding. Use it only when the
current local database can be replaced.

For a reviewer-ready fresh run, select:

- scenario: `showcase_rich`
- **Re-seed first**: checked
- **Reset database**: checked only after explicit approval

If you are preserving local investigation data, leave **Reset database**
unchecked and expect previous artifacts to affect counts.

## Expected pipeline shape

For `showcase_rich`, the expected phase order is:

```text
data -> modeling -> decision -> portfolio -> planning -> knowledge -> verify -> agents -> ops -> cleanup
```

Expected step count: **24**.

`demo_minimal` and `sparse` keep the legacy 11-step shape, grouped under the
same phase vocabulary.

## Run the demo

1. Open `/showcase`.
2. Select `showcase_rich` in the scenario picker.
3. Check **Re-seed first**.
4. Check **Reset database** only if a destructive fresh-DB run is approved.
5. Click **Run pipeline**.
6. Watch the phase accordion progress.
7. After completion, review the summary banner, KPI strip, run history, and
   Inspect Artifacts panel.

The page streams step events over `/demo/stream`. Only one pipeline may run at
a time. If a run is active, a second run attempt should be rejected rather than
starting another pipeline.

## Phase-by-phase review

### Data

Expected steps:

- `precheck`
- `reset`
- `seed`
- `status`
- `features`
- `phase2_enrichment`
- `historical_backfill`

The Data phase checks health, optionally resets and seeds the database,
computes feature inputs, enriches retail-depth tables, and creates historical
activity for the demo world.

Success indicators:

- `status` surfaces a store/product grain.
- `features` completes.
- `phase2_enrichment` does not raise a duplicate-key error.
- `historical_backfill` either completes or skips with a clear short-window
  explanation.

Real failures usually indicate Postgres, migration, or seed-state problems.

### Modeling

Expected steps:

- `train`
- `v2_train`

The demo trains the baseline models and one V2 `prophet_like` feature-aware
run. The V2 run should surface a `v2_run_id` and link to a Run Detail page
where the Feature Frame panel can be inspected.

Use the V2 run to verify that feature-frame metadata is visible to reviewers.
The demo intentionally uses `prophet_like` for the V2 panel because it exposes
signed coefficients; histogram-gradient models do not expose
`feature_importances_`.

### Decision

Expected steps:

- `backtest`
- `register`
- `champion_compat_compare`
- `stale_alias_trigger`
- `safer_promote_flow`

The Decision phase demonstrates model comparison and registry decision
workflows. It should show horizon bucket metrics, register a winner, compare
V1 and V2 runs, create a stale-alias condition, and exercise the safer-promote
path.

Inspect links should lead to Run Detail, Run Compare, or Ops surfaces,
depending on the step.

### Portfolio

Expected step:

- `batch_preset`

This step submits a small batch sweep over a limited store/product/model
matrix. It should report `completed_items` when the batch finishes.

Open `/visualize/batch` or the batch detail link to inspect the batch
runner result.

### Planning

Expected steps:

- `scenario_simulate_and_save`
- `multi_plan_compare`

The Planning phase simulates and saves a price-cut scenario, then compares
multiple saved plans. Open `/visualize/planner` to verify the saved scenario
and comparison output.

Known limitation: issue #324 tracks a fresh-DB cascade where
`safer_promote_flow` can leave a placeholder `artifact_uri` that
`scenario_simulate_and_save` cannot parse. If the run fails here with
`Cannot parse artifact-key from artifact_uri`, treat it as the documented
#324 limitation rather than a new PRP-41 regression.

### Knowledge

Expected steps:

- `embedding_provider_probe`
- `rag_index_subset`
- `rag_retrieve_probe`

The Knowledge phase probes provider health, indexes a curated subset of
`docs/user-guide/`, and runs a semantic retrieve smoke test.

If the embedding provider is unreachable, the RAG steps should skip with a
clear message. If indexing succeeds, open `/knowledge` and verify that the
user-guide corpus and search behavior are visible.

### Verify

Expected step:

- `verify`

This step checks the registered artifact when the artifact root is compatible.
For V2 winners, a skip can be expected because the V2 model uses the full
`artifacts/models/...` path while registry verification resolves under a
different root.

### Agents

Expected step:

- `agent_hitl_flow`

When the required LLM key is available, the pipeline opens an agent session
and asks the agent to trigger a `save_scenario` tool call. The step card can
show an approval state and a one-click **Approve** button.

Expected behavior:

- Missing API key: skip, not fail.
- Approval shown: clicking **Approve** should advance the step.
- Double approval: a backend 4xx after the frontend pre-approves should be
  absorbed, not surfaced as a user-visible failure.
- Timeout: skip with a clear timeout message.

Open `/chat` to inspect the transcript when the HITL flow runs.

### Ops

Expected step:

- `ops_snapshot`

The Ops phase calls:

- `/ops/summary`
- `/ops/retraining-candidates?limit=5`
- `/ops/model-health?limit=5`

The step should show a compact snapshot of stale aliases, retraining queue,
total runs, total aliases, and degrading-health grains. It should warn only
when all ops calls fail.

Open `/ops` to inspect the full operations surface.

### Cleanup

Expected step:

- `cleanup`

Cleanup closes the demo flow and attempts to restore temporary state such as
alias changes where applicable. The pipeline should then emit a final summary.

## UI surfaces to verify

### Scenario picker

- `demo_minimal`, `showcase_rich`, and `sparse` are available.
- Changing the scenario while idle changes the displayed step list.
- The picker is disabled while the pipeline is running.

### Phase accordion

- The active phase opens while the run progresses.
- After the run completes, every phase remains manually clickable.
- This verifies the issue #311 fix.

### KPI strip

The strip should appear after the first terminal step and eventually reflect:

- Runs registered
- Aliases live
- Batch items
- Plans saved
- RAG chunks

Provider skips may leave some values blank or unavailable. That is acceptable
when the corresponding step did not run.

### Step cards

Check that status, detail text, mini summaries, and Inspect buttons match the
step. Important mini summaries include backtest buckets, champion
compatibility, batch completion, scenario deltas, RAG chunks, HITL approval,
and ops snapshot.

### Stop button

During a run, click **Stop** only if you are explicitly testing cancellation.
The page should return to idle and release the pipeline lock. Partial artifacts
may remain; that is expected because the backend does not roll back
operator-visible side effects.

### Run history

After completion, the run should be stored in browser localStorage under:

```text
forecastlab.showcase.runs.v1
```

The UI keeps the last five runs, supports **Replay**, and supports **Clear**.
No server-side table is used.

### Inspect Artifacts panel

The post-run panel should render ten cards:

1. Forecast (V1+V2 ready)
2. Backtest with horizon buckets
3. Portfolio sweep
4. Saved scenario plans
5. Multi-run registry
6. V2 Feature Frame panel
7. "Not comparable" diff
8. Stale-alias + Model Health
9. Indexed corpus + search probe
10. Agent transcript

Cards can be disabled when their source step skipped or failed. Disabled cards
should explain the missing dependency.

## Route inspection checklist

After a successful or mostly successful run, inspect:

- `/visualize/forecast` — trained grain and V1/V2 controls.
- `/visualize/backtest` — RMSE and horizon bucket metrics.
- `/visualize/batch` — latest batch and completed item counts.
- `/visualize/planner` — saved scenario plans and comparison.
- `/explorer/runs` — registered model runs.
- `/explorer/runs/{v2_run_id}` — V2 Feature Frame panel.
- `/explorer/runs/compare?a={v1}&b={v2}` — compatibility verdict.
- `/ops` — stale alias and model-health information.
- `/knowledge` — indexed user-guide docs and semantic search.
- `/chat` — agent transcript, if the HITL flow ran.

## Troubleshooting

### Browser cannot reach backend

Check `frontend/.env`:

```bash
VITE_API_BASE_URL=http://localhost:8123
```

Restart Vite after changing it.

### Pipeline could not start

Another run may already be active. Wait, or use **Stop** on the active run.
The backend allows only one pipeline at a time.

### Missing LLM key

`agent_hitl_flow` may skip with a message about no API key matching
`agent_default_model`. This is expected and should not fail the pipeline.

### RAG provider unreachable

`embedding_provider_probe` can report `reachable=false`. The downstream RAG
steps should skip. Configure OpenAI/Ollama consistently if you need the
Knowledge phase to fully run.

### Postgres unavailable

Start Docker and migrate:

```bash
docker compose up -d
uv run alembic upgrade head
```

### Stale backend or frontend process

If behavior does not match the current branch, check for old `uvicorn` or
Vite processes on ports `8123` and `5173`, stop them, and restart both
services.

### Known #324 cascade

If `scenario_simulate_and_save` fails with:

```text
Cannot parse artifact-key from artifact_uri
```

the run likely hit the known safer-promote/scenario-replay cascade tracked in
issue #324. The current workaround is to document the failure and rerun after
the follow-up fix lands. Do not hide this in reviewer demos.

## Pass/fail criteria

Pass the manual dogfood when:

- `/showcase` loads and starts the run.
- `showcase_rich` shows 24 steps across the expected 10 phases.
- The phase accordion remains clickable after completion.
- KPI strip and Inspect Artifacts panel render.
- Run history persists the run.
- Stop releases the run lock when tested.
- Missing LLM/RAG providers produce skip/warn states, not crashes.
- Important Inspect links open valid pages.

Fail or block release-readiness when:

- the frontend page crashes,
- the WebSocket cannot start,
- the pipeline lock remains stuck,
- an undocumented 500 appears,
- the run cannot reach the reviewer-critical phases because of #324,
- or the UI claims success while the underlying artifact is missing.

## Recommended release-readiness order

For the cleanest demo:

1. Fix issue #324.
2. Run the fresh-DB `/showcase` dogfood with `showcase_rich`.
3. Capture screenshots for the walkthrough placeholders.
4. Cut the `dev -> main` release PR.

The current guide intentionally documents #324 as a known limitation until it
is fixed.
