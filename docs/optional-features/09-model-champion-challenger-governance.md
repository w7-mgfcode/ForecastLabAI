# Model Champion/Challenger Governance

## Summary

Add formal promotion gates for model aliases: compare champion vs
challenger, validate metrics, verify artifacts, check data freshness,
require approval, and record the decision.

## Why It Fits ForecastLabAI

The registry already stores runs, metrics, artifacts, aliases, hashes, and
statuses. Agents already require approval for sensitive actions. This
feature makes promotion decisions explicit and auditable.

## Comparable-run rule (PRP-36)

A run is comparable to another only when **all three** hold:

1. Same `(store_id, product_id)` grain.
2. **Overlapping** `data_window_start` / `data_window_end`.
3. **Same `feature_frame_version`** — read from `runtime_info.feature_frame_version`
   on the registry row; legacy rows without the key are treated as V1.

The third clause is load-bearing — a V1 run and a V2 run with otherwise
identical fields are **not** duplicates and **not** comparable. Promoting
a V1 alias over a V2 challenger (or vice versa) would silently change
the feature contract the alias points at.

`RegistryService.find_comparable_runs(...)` is the canonical query and
`OpsService.get_summary` uses the same predicate to classify staleness.
When an alias's run has `V_a` and a newer comparable SUCCESS run has
`V_b != V_a`, the alias is marked `is_stale=true` with
`stale_reason="feature_frame_version_mismatch"` (a distinct value from
`newer_success_run`) so Slice C can render the mismatch separately.

## User Value

- Users understand why a model became production.
- Bad models are blocked from promotion.
- Governance improves the credibility of the demo.
- Agent recommendations become safer because they pass deterministic gates.

## Proposed Workflow

1. Select current champion alias.
2. Select challenger run.
3. Run promotion checks:
   - Better WAPE/sMAPE/MAE.
   - Bias within threshold.
   - Stability within threshold.
   - Artifact hash present and verified.
   - Data window is recent.
   - Backtest exists.
   - No failed quality checks.
4. Show pass/fail report.
5. Request approval.
6. Promote alias and store decision record.

## Backend Design

Candidate endpoints:

- `POST /registry/promotion-checks`
- `POST /registry/aliases/{alias}/promote`
- `GET /registry/promotion-decisions`

Possible new table:

- `promotion_decision`

Fields:

- `decision_id`
- `alias`
- `champion_run_id`
- `challenger_run_id`
- `gate_results`
- `approved_by`
- `approved_at`
- `decision`
- `reason`

## Frontend Design

Add to:

- Run Compare page.
- Run Detail page.
- Admin Deployment Aliases tab.
- Future ForecastOps Control Center.

Display:

- Champion/challenger metric diff.
- Gate report.
- Artifact integrity.
- Approval controls.
- Decision history.

## MVP Scope

- Gate-check endpoint.
- Promotion report UI.
- Manual approval button.
- Decision persisted in registry metadata or a new table.

## Full Version

- Configurable promotion policies.
- Agent-generated promotion recommendation.
- Quality-check integration.
- Rollback alias action.
- Promotion audit export.

## Risks

- Promotion policy can be too strict for demo data.
- Metrics from different data windows should not be compared blindly.
- Alias mutation must be atomic.
- Approval records should be immutable.

## Validation Plan

- Unit tests for gate logic.
- API tests for pass/fail scenarios.
- Integration tests for alias mutation.
- Browser QA for compare, gate report, approve, and decision history.

## Documentation

- MLflow Model Registry documentation: https://www.mlflow.org/docs/latest/ml/model-registry/
- MLflow model aliases documentation: https://www.mlflow.org/docs/latest/ml/model-registry/workflow/
- scikit-learn model persistence: https://scikit-learn.org/stable/model_persistence.html
- scikit-learn TimeSeriesSplit: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- FastAPI documentation: https://fastapi.tiangolo.com/
- SQLAlchemy asyncio documentation: https://docs.sqlalchemy.org/en/21/orm/extensions/asyncio.html
- Pydantic AI documentation: https://ai.pydantic.dev/
- NIST AI Risk Management Framework: https://www.nist.gov/itl/ai-risk-management-framework
- OWASP Top 10 for LLM Applications: https://owasp.org/www-project-top-10-for-large-language-model-applications/
