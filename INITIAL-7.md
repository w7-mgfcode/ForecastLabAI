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
- Lifecycle Management:
  - State machine tracking: PENDING | RUNNING | SUCCESS | FAILED | ARCHIVED.
  - Deployment Aliases: Mutable pointers (e.g., 'prod-v1') to specific successful runs.
- Metadata & Lineage:
  - JSONB storage for ModelConfig, FeatureConfig, and Performance Metrics.
  - Runtime Snapshot: Recording Python/Library versions for environment parity.
  - Agent Context: Integration of agent_id and session_id for autonomous run traceability.
- Artifact Integrity:
  - Checksum-based verification (SHA-256) for all serialized artifacts.
- Storage Strategy:
  - Pluggable storage providers (LocalFS, future S3/GCS) via Abstract Registry Interface.

## EXAMPLES:
- `examples/registry/create_run.py` — create run record + persist configs.
- `examples/registry/list_runs.py` — leaderboard preview.
- `examples/registry/compare_runs.py` — compare two runs (metrics + configs).

## DOCUMENTATION:
- Postgres JSONB patterns
- Artifact integrity (hashing) best practices
- [Using JSONB in PostgreSQL](https://scalegrid.io/blog/using-jsonb-in-postgresql-how-to-effectively-store-index-json-data-in-postgresql/)
- [Supply Chain Vulnerability](https://www.fortra.com/blog/supply-chain-vulnerability)

## OTHER CONSIDERATIONS:
- No hardcoded artifact paths: derived from `ARTIFACT_ROOT` + run_id.
- Policy for duplicate runs (same config/window) must be Settings-driven (allow/deny/detect).
