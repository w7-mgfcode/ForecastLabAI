# INITIAL-7.md — Model Registry + Artifacts + Reproducibility

## FEATURE:
- Run registry captures:
  - run_id, timestamps
  - model_type + model_config JSON
  - feature_config JSON + schema_version
  - data window boundaries
  - metrics JSON
  - artifact_uri + artifact hash
  - optional git_sha
- Artifact storage abstraction:
  - local filesystem by default (Settings-driven)
  - compatible with future S3-like storage backends

## EXAMPLES:
- `examples/registry/create_run.py` — create run record + persist configs.
- `examples/registry/list_runs.py` — leaderboard preview.
- `examples/registry/compare_runs.py` — compare two runs (metrics + configs).

## DOCUMENTATION:
- Postgres JSONB patterns
- Artifact integrity (hashing) best practices

## OTHER CONSIDERATIONS:
- No hardcoded artifact paths: derived from `ARTIFACT_ROOT` + run_id.
- Policy for duplicate runs (same config/window) must be Settings-driven (allow/deny/detect).
