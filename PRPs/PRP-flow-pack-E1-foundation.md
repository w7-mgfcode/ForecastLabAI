name: "PRP — flow-pack E1 Foundation (tracked contract + /flow-prime + rule + local install)"
description: |
  Foundation slice of the flow: command-suite integration. Lands the tracked durable
  source-of-truth (docs/flow-pack/**) plus the first command (/flow-prime) and the
  umbrella-issue rule as a regenerable local install under .claude/**. Blocks E2–E5.

<!-- provenance: reverse-engineered from
  /home/w7-hector/_KB-BASE-BY-w7/JOB/DIA-FLOW/ai_engineering_mermaid_flow_pack/docs/flow-analysis/{01,02,03}.md
  + context-engineering-intro-main/use-cases/build-with-agent-team.
  Working analysis: .flow/state.md + .flow/brainstorm-log.md (Phases 0–5). -->

## Issue links
- Umbrella: **#368** — feat(repo): integrate flow-pack methodology as the flow: command suite
- This epic: **#369** — flow-pack E1 — foundation (minimal viable; BLOCKS E2–E5)
- Milestone: **#1 flow-pack-suite** · labels: `epic`, `flow`

---

## Goal
Implement the **E1 foundation** of the `flow:` command suite: a tracked, durable methodology
contract and the first command, installed locally per the **durable-source split**. The end
state: a reviewer on a fresh clone can read `docs/flow-pack/**`, regenerate the local
`.claude/commands/flow/` install, and run `/flow-prime` to produce a current-workflow-map +
"you are here" snapshot written to `.flow/state.md`.

**Deliverable:** 4 files + 1 documented recovery path (see Desired tree). No E2–E5. No GitHub
issue creation. No commit/push.

## Why
- `.claude/` is gitignored (CLAUDE.md "Learnings"), so commands/rules placed only there are lost
  on a fresh clone and cannot be the source of truth. E1 establishes the tracked `docs/flow-pack/**`
  as durable, with `.claude/**` as a regenerable runtime install.
- E1 is the minimal viable slice that proves the loop and unblocks the parallel epics E2–E4.

## What
A docs-first foundation: tracked contract + tracked command template → local install → working
`/flow-prime`.

### Success Criteria
- [ ] Tracked `docs/flow-pack-methodology.md` exists (Mermaid pipeline + invariants + FLAI mapping
      + portability manifest + a "Fresh-clone recovery" section).
- [ ] Tracked `docs/flow-pack/commands/flow-prime.md` exists (the canonical command template/spec).
- [ ] Local `.claude/commands/flow/flow-prime.md` present, byte-regenerable from the tracked template.
- [ ] Local `.claude/rules/umbrella-issue.md` present (durable narrative lives in the methodology doc).
- [ ] Fresh-clone recovery documented and verified: `cp docs/flow-pack/commands/*.md .claude/commands/flow/`
      reproduces the local command(s).
- [ ] `/flow-prime` runs: delegates to `core_piv_loop:prime` (codebase) + gathers gh state + writes
      `.flow/state.md`; output includes a current-workflow-map and a you-are-here snapshot.
- [ ] Every created artifact carries a provenance header linking to its KB source.
- [ ] `git check-ignore .claude/commands/flow/flow-prime.md` confirms the local copy is NOT tracked;
      `git status` shows `docs/flow-pack/**` as the only NEW tracked additions.

## All Needed Context

### Documentation & References
```yaml
# MUST READ — the reverse-engineered methodology (already analyzed in Phases 0–2)
- file: .flow/state.md
  why: the full Phase 0–5 decision record — chosen workflow, durable-source split, epic plan
- file: .flow/brainstorm-log.md
  why: the V1→V2 dogfood, 5-dim scores, and the 3-subagent research findings E1 is built on

- file: /home/w7-hector/_KB-BASE-BY-w7/JOB/DIA-FLOW/ai_engineering_mermaid_flow_pack/docs/flow-analysis/01-decomposition.md
  why: umbrella 7-field contract + epic phase taxonomy (foundation/parallel/release) + hierarchy-as-data — the umbrella-issue.md rule is reverse-engineered from this
- file: /home/w7-hector/_KB-BASE-BY-w7/JOB/DIA-FLOW/ai_engineering_mermaid_flow_pack/docs/flow-analysis/03-continuation-discipline.md
  why: baseline → V1 → 3 read-only agents → score → V2; /flow-prime captures the "baseline reality" step
- file: /home/w7-hector/_KB-BASE-BY-w7/JOB/DIA-FLOW/ai_engineering_mermaid_flow_pack/docs/flow-analysis/02-execution-pipeline.md
  why: the issue→5-subtask pipeline = the existing issue-to-subtasks skill; flow: hands off, does not reimplement

# PATTERNS TO MIRROR (house style — match exactly)
- file: .claude/commands/core_piv_loop/prime.md
  why: /flow-prime DELEGATES to this for codebase priming; mirror its command structure + section style
- file: .claude/rules/commit-format.md
  why: rule anatomy to mirror (Title → Purpose → Rules/tables → Examples → Before X checklist)
- file: .claude/rules/branch-naming.md
  why: second rule-style reference; also dictates the branch name for this work
- file: .claude/commands/base_prp/prp-create.md
  why: the hand-off target invoked per epic after /flow-epics

# CONSTRAINTS
- file: CLAUDE.md
  section: "Learnings" — ".claude/ is gitignored — skills, rules, and hooks are local-only"
  critical: this is WHY the durable-source split exists; do not treat .claude/** as committed truth
- file: .gitignore
  why: confirm /.claude and .claude are ignored; .flow/ is local working state (consider ignoring it too)
```

### Current Codebase tree (relevant slice)
```bash
.claude/
  commands/{base_cm,base_evals,base_prp,core_piv_loop,do,git-operations,prompts,validation}/  # NO flow/ yet
  rules/{branch-naming,commit-format,output-formatting,product-vision,security-patterns,shadcn-ui,test-requirements,ui-design,versioning}.md  # NO umbrella-issue.md yet
docs/        # tracked; NO flow-pack/ yet
.flow/       # working state (untracked): state.md, brainstorm-log.md
PRPs/        # this PRP lives here
```

### Desired Codebase tree (files to add + responsibility)
```bash
docs/
  flow-pack-methodology.md                 # TRACKED durable contract: Mermaid pipeline, invariants, FLAI mapping, portability manifest, fresh-clone recovery
  flow-pack/
    commands/
      flow-prime.md                        # TRACKED canonical template/spec for /flow-prime (source of truth)
.claude/
  commands/flow/
    flow-prime.md                          # LOCAL install — regenerable byte-copy of the tracked template (gitignored, NOT durable)
  rules/
    umbrella-issue.md                      # LOCAL rule — agent contract; durable narrative is in docs/flow-pack-methodology.md
```

### Known Gotchas & Quirks
```text
# CRITICAL: .claude/ is gitignored (/.claude and .claude in .gitignore). The local command +
#   rule are NEVER the committed source. Durable truth = docs/flow-pack/**. Verify with:
#   git check-ignore .claude/commands/flow/flow-prime.md   (must print the path = ignored)
# CRITICAL: the local install must be a faithful regeneration of the tracked template, NOT a
#   hand-edited divergent copy. If they drift, the tracked template wins. Recovery = cp.
# GOTCHA: commit-format.md requires every commit reference an open issue → commit against (#369);
#   branch off dev per branch-naming.md, e.g. feat/flow-pack-e1-foundation.
# GOTCHA: /flow-prime must DELEGATE to core_piv_loop:prime for codebase priming (do NOT duplicate
#   its git ls-files/tree/log logic) and ADD only the gh-state + you-are-here + .flow/state.md write.
# GOTCHA: .flow/ is local working state. Consider adding `.flow/` to .gitignore so it is not
#   accidentally committed (optional task T6; respect the dirty worktree — do not stage uv.lock or
#   docker-compose.lan.yml).
# SCOPE: do NOT create flow-analyze/brainstorm/umbrella/epics commands here — E1 ships /flow-prime
#   only. /flow-analyze is permanently deferred (folded into prime/brainstorm).
# PROVENANCE: every file starts with an HTML-comment provenance header naming its KB source.
# NO new runtime deps, no agent-teams/tmux (research fan-out = plain read-only subagents).
```

## Implementation Blueprint

### list of tasks (dependency order)
```yaml
Task 1 — CREATE docs/flow-pack-methodology.md (tracked source of truth):
  - INCLUDE: a Mermaid diagram of the 4-command pipeline (see .flow/state.md "Chosen workflow")
  - INCLUDE: invariants list (read-only-until-approval; hierarchy-as-data; exactly-3 research agents;
    score bands >=40/36-39/<36; 7-field umbrella; foundation->parallel->release; every defer has a reason)
  - INCLUDE: FLAI mapping table (which methodology stage = which flow: command / existing skill)
  - INCLUDE: "Durable-source split" section (docs/flow-pack/** tracked vs .claude/** local install)
  - INCLUDE: "Fresh-clone recovery" section with the exact cp command
  - INCLUDE: "Portability manifest" — the named params to change to reuse in another repo
  - HEADER: provenance comment -> flow-analysis/{01,02,03}.md

Task 2 — CREATE docs/flow-pack/commands/flow-prime.md (tracked command template):
  - MIRROR structure of: .claude/commands/core_piv_loop/prime.md (frontmatter? section headings, $ARGUMENTS)
  - SPEC the /flow-prime behavior: (a) delegate to core_piv_loop:prime; (b) gather gh state
    (gh issue list, milestones, releases, project); (c) emit current-workflow-map + you-are-here;
    (d) write/append .flow/state.md; (e) print gate result + next command (/flow-analyze folded in or
    /flow-brainstorm) per the self-guiding convention
  - INCLUDE dry-run note + provenance header

Task 3 — INSTALL .claude/commands/flow/flow-prime.md (local runtime copy):
  - REGENERATE as a byte-copy of docs/flow-pack/commands/flow-prime.md (cp), so they never diverge
  - VERIFY: diff docs/flow-pack/commands/flow-prime.md .claude/commands/flow/flow-prime.md == empty

Task 4 — CREATE .claude/rules/umbrella-issue.md (local rule):
  - MIRROR anatomy of: .claude/rules/commit-format.md
  - CONTENT (from Phase 4 draft in .flow + 01-decomposition.md): when to create an umbrella;
    7-field body contract; epic shape + phase contract; hierarchy-as-data (gh api sub_issues, no native
    gh cmd); labels+milestone; write discipline (dry-run/idempotent/approval-gated); the command
    source-of-truth & install split + recovery; validation (run audit-rules-drift)
  - HEADER: provenance + "durable copy: docs/flow-pack-methodology.md"

Task 5 — DOCUMENT fresh-clone recovery (in Task 1 doc, verify here):
  - The methodology doc's recovery section reproduces .claude/commands/flow/ from docs/flow-pack/commands/

Task 6 (OPTIONAL) — MODIFY .gitignore:
  - ADD `.flow/` so local working state is not accidentally committed
  - PRESERVE existing entries; do NOT touch uv.lock / docker-compose.lan.yml in the worktree
```

### Per-task notes
```text
# Task 2 — /flow-prime spec is a DELEGATION wrapper, not a reimplementation:
#   "Run core_piv_loop:prime for codebase priming, THEN gather gh state, THEN synthesize the
#    current-workflow-map + you-are-here, write .flow/state.md, and print the next-command pointer."
# Task 4 — the rule is the LOCAL agent contract; keep it short and point to docs/flow-pack-methodology.md
#   for the full narrative (avoid duplicating, since the rule isn't committed).
```

### Integration Points
```yaml
DOCS (tracked):
  - add: docs/flow-pack-methodology.md, docs/flow-pack/commands/flow-prime.md
CLAUDE (local, gitignored):
  - add: .claude/commands/flow/flow-prime.md, .claude/rules/umbrella-issue.md
GITIGNORE (optional):
  - add: ".flow/"
HAND-OFF:
  - on E1 completion, E2–E4 each go to base_prp:prp-create (separate, later)
```

## Validation Loop

### Level 1: File presence + durable-source split
```bash
# tracked source of truth exists
test -f docs/flow-pack-methodology.md && test -f docs/flow-pack/commands/flow-prime.md && echo "OK tracked"
# local install exists and is gitignored (NOT durable)
test -f .claude/commands/flow/flow-prime.md && test -f .claude/rules/umbrella-issue.md && echo "OK local"
git check-ignore .claude/commands/flow/flow-prime.md .claude/rules/umbrella-issue.md   # both must print (ignored)
# local install == tracked template (no drift)
diff -q docs/flow-pack/commands/flow-prime.md .claude/commands/flow/flow-prime.md && echo "OK no drift"
# only docs/flow-pack/** are NEW tracked files (plus this PRP); .claude/** not staged
git status --short
```

### Level 2: Fresh-clone recovery reproduction
```bash
# simulate recovery: blow away the local install, regenerate from tracked template, confirm identical
rm -f .claude/commands/flow/flow-prime.md
cp docs/flow-pack/commands/*.md .claude/commands/flow/
diff -q docs/flow-pack/commands/flow-prime.md .claude/commands/flow/flow-prime.md && echo "OK recovery reproduces local"
```

### Level 3: /flow-prime smoke
```bash
# In a Claude Code session, run the command and confirm it produces the two artifacts:
#   - a current-workflow-map (existing commands/skills/rules/workflows)
#   - a you-are-here snapshot (branch, version, open issues, gap)
# and writes or appends to `.flow/state.md`. Confirm it ends by printing the next-command pointer.
# (No automated assertion — this is an interactive command; verify the output sections exist.)
```

## Tests / checks required
- [ ] Level 1 file-presence + gitignore + no-drift checks all pass.
- [ ] Level 2 recovery reproduces the local install byte-for-byte.
- [ ] Level 3 `/flow-prime` produces both required output sections + writes `.flow/state.md`.
- [ ] `audit-rules-drift` skill run against the new `umbrella-issue.md` reports no drift from AGENTS.md/CLAUDE.md.
- [ ] Provenance header present in all 4 created files (`grep -l provenance` finds each).
- [ ] No standard repo gate is broken (markdown-only change → ruff/mypy/pyright/pytest unaffected; run them to confirm green if any tooling touches docs).

## Final Validation Checklist
- [ ] All 4 files created + recovery path documented and verified.
- [ ] Durable-source split holds: `docs/flow-pack/**` tracked; `.claude/**` ignored + regenerable.
- [ ] `/flow-prime` runs and writes `.flow/state.md`.
- [ ] `umbrella-issue.md` mirrors house rule anatomy; `audit-rules-drift` clean.
- [ ] E2–E5 NOT implemented; no new GitHub issues created.
- [ ] Branch is `feat/flow-pack-e1-foundation` off `dev`; commit (when the user authorizes) references `(#369)`.
- [ ] No commit/push performed by this PRP execution unless explicitly requested; `uv.lock` + `docker-compose.lan.yml` left untouched.

## Anti-Patterns to Avoid
- ❌ Treating `.claude/commands/flow/` as the source of truth (it's gitignored — use `docs/flow-pack/**`).
- ❌ Reimplementing codebase priming in `/flow-prime` instead of delegating to `core_piv_loop:prime`.
- ❌ Building flow-analyze/brainstorm/umbrella/epics here — E1 is `/flow-prime` only.
- ❌ Letting the local install drift from the tracked template.
- ❌ Creating GitHub issues, committing, or pushing as part of E1 implementation.
- ❌ Staging `uv.lock` / `docker-compose.lan.yml` (pre-existing dirty worktree — leave alone).

---

## Confidence Score: 8/10
One-pass likelihood is high: the methodology is fully reverse-engineered and dogfooded (`.flow/`),
all dependencies are confirmed, and the work is markdown-only (no runtime/type risk). −2 for the
two judgement-heavy authoring tasks (the `/flow-prime` delegation spec and the rule's fidelity to
house style) and the gitignore split, which a careless executor can get subtly wrong.
