# ForecastLabAI — Claude Code Operating Index

> **Read `@AGENTS.md` first.** It is the shared cross-tool brief — stack, setup, build/test
> commands, validation gates, architecture, conventions, safety, and git flow. This file adds
> only Claude-specific operating context on top; it does not repeat AGENTS.md content.

@AGENTS.md

## Deep-Dive References

Claude pulls these in on demand — load only what the task touches.

- Developer guide & tech stack:  @docs/_base/DEV_GUIDE.md
- Architecture & boundaries:     @docs/_base/ARCHITECTURE.md
- API contracts & interfaces:    @docs/_base/API_CONTRACTS.md
- Operational runbooks:          @docs/_base/RUNBOOKS.md
- Security & compliance:         @docs/_base/SECURITY.md
- Rules & constraints:           @docs/_base/RULES.md
- Domain model & glossary:       @docs/_base/DOMAIN_MODEL.md
- Service & dependency map:      @docs/_base/REPO_MAP_INDEX.md
- Pipeline contract (CI/CD):     @docs/_base/PIPELINE_CONTRACT.md

> Project rules are enforced via `.claude/rules/` (commit-format, branch-naming,
> security-patterns, product-vision, test-requirements, ui-design, versioning,
> output-formatting). Read those first — they are authoritative on detail.

## Safety

Full constraint matrix: `docs/_base/RULES.md`. Hard rules and stop-and-ask gates: `@AGENTS.md`
§ Safety. When a change is ambiguous or hard to reverse, surface the concern before acting.

## Verification

```bash
uv run ruff check . && uv run mypy app/ && uv run pyright app/ && uv run pytest -v -m "not integration"
gh issue view <N> --json state                # confirm the referenced issue exists
wc -l CLAUDE.md                                # must stay ≤ 150
```

## Workflow

1. Open or pick a GitHub issue (`gh issue list`); branch off `dev` per `branch-naming.md`.
2. Implement inside the matching `app/features/<slice>/` (or a new slice with a PRP).
3. Run the validation gates (`@AGENTS.md` § Validation Gates) locally before pushing.
4. (DB/UI touched) Run integration tests + frontend type-check + dogfood via the webapp-testing skill.
5. Commit `type(scope): description (#issue)`; push; open a PR into `dev`; merge once CI is green.
6. Release: PR `dev` → `main`; merge the release-please Release PR to tag `vX.Y.Z`.

## Learnings

- HEURISTIC_MODE generated `docs/_base/` (no `docs/_kB/repo-map/` KB). Run `mapping-repo-context`
  to upgrade fidelity; `[ASSUMPTION]`-marked sections in `docs/_base/` need verification.
- `.claude/` is gitignored — skills, rules, and hooks are local-only and never appear in commits or PRs.
- AGENTS.md is the universal agent brief; CLAUDE.md is the Claude-specific layer that imports it.
  Keep shared content in AGENTS.md only — never duplicate it here.
