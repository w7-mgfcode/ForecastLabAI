name: "PRP — flow-pack E4 /flow-epics (tracked template + local install + epic decomposition + sub-issue linking)"
description: |
  E4 of the flow: command-suite integration. Ships the /flow-epics command: reads an umbrella
  issue decomposition, creates phase-ordered epic issues with idempotent guards, links them as
  sub-issues via the GitHub REST API, and hands off to base_prp:prp-create per epic.
  Parallel epic — runs after E1 (#369 merged). Docs-only: no app/backend/frontend changes.

<!-- provenance: docs/flow-pack-methodology.md § "/flow-epics — epic issues" + § "Epic contract"
     + § "Hierarchy-as-data (REST API)" + § "Durable-source split".
     Epic scope: GitHub issue #373 body.
     Structural pattern: PRPs/PRP-flow-pack-E1-foundation.md -->

## Issue links
- Umbrella: **#368** — feat(repo): integrate flow-pack methodology as the flow: command suite
- This epic: **#373** — flow-pack E4 — /flow-epics (epic decomposition, sub-issue linking, prp-create handoff)
- Milestone: **#1 flow-pack-suite** · labels: `epic`, `flow`

---

## Goal

Implement the **E4 deliverable** of the `flow:` command suite: the `/flow-epics` command.

End state: a user can run `/flow-epics 368` (or `/flow-epics #368`) and the command will:
1. Read umbrella #368's decomposition section to build an epic inventory
2. Check which epics already exist (title search) and which are already linked (GraphQL)
3. For each epic not yet a sub-issue: dry-run echo → user "approve" → `gh issue create` → rate-delay → `gh api` sub-issue link
4. Skip E5 Release gate (deferred per #373 scope)
5. Verify the final sub-issue list via GraphQL
6. Print gate result + per-epic handoff to `base_prp:prp-create`

**Deliverable:** 2 files + 1 documented recovery path (see Desired tree). No E2/E3/E5 behavior.
No app/backend/frontend code changes. No commit/push without explicit user authorization.

## Why

- The `flow:` suite's value ends at `/flow-umbrella` unless epics exist as linked sub-issues.
  `/flow-epics` closes the loop: umbrella → epics → base_prp:prp-create per epic.
- Hierarchy-as-data (REST sub-issue API) is required so project-board grouping, closure rollup,
  and dependency ordering work natively. Body `#N` mentions alone are documentation, not data.
- E4 is parallel with E2/E3; it can ship independently once E1 is merged.
- The write-discipline invariants (dry-run/idempotent/approval/rate-delay/confirm) are already
  fully specified in `docs/flow-pack-methodology.md` and `.claude/rules/umbrella-issue.md` —
  this PRP operationalises them into a reusable slash-command.

## What

A docs-first deliverable: tracked canonical template → local runtime install → working `/flow-epics`.

### Success Criteria
- [ ] Tracked `docs/flow-pack/commands/flow-epics.md` exists with a complete, self-contained
      command spec (all 8 required sections — see Task 1).
- [ ] Local `.claude/commands/flow/flow-epics.md` present, byte-regenerable from the tracked template.
- [ ] Fresh-clone recovery documented and verified:
      `cp docs/flow-pack/commands/*.md .claude/commands/flow/` reproduces both command files.
- [ ] Running `/flow-epics 368` shows a correct inventory (E1 exists/linked, E2–E4 exist, E5 deferred)
      without writing anything until the user approves.
- [ ] Every dry-run echo shows the exact `gh issue create` + `gh api sub_issues POST` commands before
      any execution.
- [ ] All created/linked epics carry labels `epic` + `flow` + `feat` + milestone `flow-pack-suite`.
- [ ] Sub-issue links verified via GraphQL after each write batch.
- [ ] No GitHub write without explicit user "approve" for each write operation.
- [ ] E5 Release gate shown as ⏭️ SKIP (deferred) — never auto-created.
- [ ] No app/backend/frontend code touched; `uv.lock` / `docker-compose.lan.yml` / uncommitted
      `flow-prime.md` left untouched.

## All Needed Context

### Documentation & References
```yaml
# SOURCE OF TRUTH — read these first
- file: docs/flow-pack-methodology.md
  section: >
    "/flow-epics — epic issues" (Step 1–4 of Stage 2 — Decompose),
    "Epic contract" (phase blockquote + Purpose + Sub-tasks),
    "Hierarchy-as-data (REST API)" (exact gh api calls),
    "Durable-source split" (tracked vs gitignored)
  why: >
    Authoritative spec; exact gh api patterns; epic body contract;
    portability invariants the command must uphold

- file: .claude/rules/umbrella-issue.md
  section: >
    "Epic body — phase contract" (blockquote templates),
    "Hierarchy-as-data" (POST endpoint, no native gh cmd),
    "Write discipline" (5-step dry-run/idempotent/approval/rate-delay/confirm),
    "Labels and milestone" (label superset rule)
  why: Rule-level contract the command encodes; exact write discipline steps

# PATTERN TO MIRROR — match structure exactly
- file: docs/flow-pack/commands/flow-prime.md
  why: >
    The only other tracked command template; mirror its YAML frontmatter,
    HTML provenance comment, section headings, $ARGUMENTS convention,
    inline !`bash` commands, and output-format block word-for-word in style

# LIVE UMBRELLA BEING SERVED
- issue: "#368"
  command: "gh issue view 368 --json number,title,body,labels,milestone"
  why: >
    Live umbrella whose Decomposition section defines which epics to create;
    its current sub-issues list is the ground truth for idempotency

# EXISTING EPICS (idempotency ground truth)
- issue: "#369 E1 Foundation — merged/linked"
- issue: "#371 E2 Parallel — /flow-brainstorm"
- issue: "#372 E3 Parallel — /flow-umbrella"
- issue: "#373 E4 Parallel — /flow-epics (this epic)"
  why: All four exist; command must detect them and skip create, only link if not yet a sub-issue

# E1 PRP STRUCTURAL REFERENCE
- file: PRPs/PRP-flow-pack-E1-foundation.md
  why: >
    Exact PRP structure pattern — frontmatter, issue links, goal/why/what,
    context YAML, current+desired trees, Known Gotchas block, task list format,
    integration points YAML, validation levels, final checklist, confidence score

# CONSTRAINTS
- file: CLAUDE.md
  section: "Learnings — .claude/ is gitignored"
  critical: >
    Local install is NOT the durable artifact. docs/flow-pack/** is tracked.
    .claude/commands/flow/flow-epics.md must be gitignored (verify with git check-ignore).

- file: .claude/rules/output-formatting.md
  why: >
    Emoji status indicators (✅ ❌ ⏭️ ⚠️ 🔄) + box-drawing separators (━━━/────)
    the command's printed output must match exactly

- file: .claude/rules/commit-format.md
  why: Branch name (feat/flow-pack-e4-flow-epics) + commit format (feat(docs,repo): ... (#373))
```

### Current Codebase tree (relevant slice)
```bash
docs/
  flow-pack-methodology.md             # TRACKED — source-of-truth spec
  flow-pack/
    commands/
      flow-prime.md                    # TRACKED — structural pattern to mirror (MODIFIED unstaged)
.claude/
  commands/flow/
    flow-prime.md                      # LOCAL — byte-copy of tracked template
  rules/
    umbrella-issue.md                  # LOCAL — write-discipline + sub-issue API contract
PRPs/
  PRP-flow-pack-E1-foundation.md       # REFERENCE — PRP structural pattern
  PRP-flow-pack-E4-flow-epics.md       # THIS PRP (being executed)
```

### Desired Codebase tree (files to add + responsibility)
```bash
docs/
  flow-pack/
    commands/
      flow-epics.md                    # TRACKED — canonical template/spec for /flow-epics
                                       # source of truth; the committed, portable contract
.claude/
  commands/flow/
    flow-epics.md                      # LOCAL install — regenerable byte-copy of the tracked
                                       # template (gitignored; NOT durable)
```

### Known Gotchas & Quirks
```text
# CRITICAL: No native `gh` sub-issue command exists (cli/cli#10298). ALWAYS use:
#   gh api repos/w7-mgfcode/ForecastLabAI/issues/{umbrella_N}/sub_issues \
#     -X POST -F sub_issue_id={epic_N} \
#     --header "GitHub-Next-Preview: true"
#   The --header "GitHub-Next-Preview: true" is REQUIRED for the REST POST write.
#   It is NOT required for GraphQL read queries.

# CRITICAL: Idempotent check BEFORE create — search by exact issue title:
#   gh issue list --search "<exact title>" --json number,title \
#     --jq '.[0].number // "none"'
#   If result != "none" → issue already exists → skip create, proceed to link check only.
#   GitHub search is fuzzy — verify the returned title matches character-for-character.

# CRITICAL: Idempotent link check — fetch current sub-issues BEFORE any POST:
#   gh api graphql -f query='
#     { repository(owner:"w7-mgfcode", name:"ForecastLabAI") {
#         issue(number: N) { subIssues(first: 20) { nodes { number title } } }
#     } }'
#   If epic_N already appears in subIssues.nodes → skip POST (already linked).

# GOTCHA: sleep 1 (rate-delay) between consecutive gh api WRITE calls — mandatory, not advisory.
#   This applies between (create + link) pairs AND between two consecutive creates.
#   Do NOT sleep between a read and a write, only between consecutive writes.

# GOTCHA: Epic title naming convention — must match the umbrella decomposition text exactly so
#   idempotent search finds existing issues:
#   Pattern from live E1–E4: "feat(repo): flow-pack <phase-label> — <scope description>"
#   Example: "feat(repo): flow-pack E5 — release gate (end-to-end dogfood + portability manifest)"

# GOTCHA: Label superset rule — epic labels must include ALL umbrella labels minus "umbrella",
#   plus "epic". Umbrella #368 has: umbrella, flow → epic labels: epic, flow, feat.
#   Read umbrella labels from: gh issue view <N> --json labels --jq '[.labels[].name]'
#   Then remove "umbrella" from the list and add "epic".

# GOTCHA: docs/flow-pack/commands/flow-prime.md is MODIFIED (not staged) in the current worktree.
#   Run `git diff docs/flow-pack/commands/flow-prime.md` before branching to see the delta.
#   Do NOT stage or commit that file as part of this PRP — it belongs to a separate fix.
#   Only stage docs/flow-pack/commands/flow-epics.md (the new tracked file).

# SCOPE BOUNDARY — E5 is DEFERRED:
#   Issue #373 Out-of-scope: "Release-gate epic (E5) — deferred until E2–E4 are implemented."
#   When the command encounters the Release-gate line in the umbrella decomposition, it MUST
#   show it as ⏭️ SKIP (deferred) and never auto-create it. This is a hard scope boundary.

# SCOPE BOUNDARY — command creates epics, nothing else:
#   - Does NOT author PRP content (→ base_prp:prp-create)
#   - Does NOT create sub-tasks within epics (→ issue-to-subtasks)
#   - Does NOT implement any epic's feature code
#   - Does NOT run any validation gates (ruff/mypy/pytest) — markdown-only change
```

## Implementation Blueprint

### Tasks (dependency order)

```yaml
Task 1 — CREATE docs/flow-pack/commands/flow-epics.md (tracked canonical template):

  MIRROR structure of: docs/flow-pack/commands/flow-prime.md
  The file must contain ALL 8 sections in this exact order:

  ── Section A: YAML frontmatter ──
    ---
    description: Create phase-ordered epic issues from an umbrella decomposition, link via REST
      sub-issues API, and hand off to base_prp:prp-create per epic
    ---

  ── Section B: HTML provenance comment ──
    <!-- provenance: docs/flow-pack-methodology.md §"/flow-epics — epic issues" + §"Epic contract"
         + §"Hierarchy-as-data (REST API)". Source of truth for .claude/commands/flow/flow-epics.md.
         Recovery: cp docs/flow-pack/commands/flow-epics.md .claude/commands/flow/flow-epics.md
         Full methodology: docs/flow-pack-methodology.md -->

  ── Section C: Title + Objective ──
    # flow-epics: Epic Decomposition
    ## Objective
    One-paragraph prose: "Read the umbrella issue's Decomposition section, create N phase-ordered
    epic issues (Foundation → Parallel → Release gate) with idempotent guards, link each as a
    sub-issue of the umbrella via the GitHub REST API, and hand off to base_prp:prp-create per
    open epic. Skips epics that already exist and/or are already linked."

  ── Section D: Arguments ──
    ## Arguments
    "$ARGUMENTS — umbrella issue number (e.g. 368 or #368). Required.
    If omitted, reads the active umbrella number from the 'In-progress issues' block in
    .flow/state.md (looks for the [umbrella,flow]-labeled entry)."

  ── Section E: Process (7 numbered steps with inline !`bash` commands) ──
    ## Process

    ### 1. Parse argument
    Strip '#' prefix from $ARGUMENTS if present.
    If empty: read .flow/state.md and find the [umbrella,flow] open issue number.
    !`cat .flow/state.md | grep "umbrella,flow" | head -1`

    ### 2. Fetch umbrella
    !`gh issue view <N> --json number,title,body,labels,milestone`
    Abort with ❌ if not found or if the `umbrella` label is absent.

    ### 3. Extract decomposition
    Parse the body: find lines between "## Decomposition" and the next "##" heading.
    For each bullet line:
      - Detect phase marker: "Foundation" / "Parallel" / "Release gate" (from the bold label)
      - Extract scope description (used to construct the epic title and Purpose)
      - Detect any embedded "#N" ref already in the line (pre-existing issue pointer)
      - Flag as SKIP if the line contains "(deferred)" OR the phase is Release gate
        AND the scope mentions "not yet created" or "deferred"

    ### 4. Pre-flight checks
    !`gh label list --json name --jq '[.[].name] | contains(["epic","flow","feat"])'`
    Abort with ❌ if result is false (missing labels).
    !`gh api repos/w7-mgfcode/ForecastLabAI/milestones --jq '.[].title'`
    Abort with ❌ if "flow-pack-suite" not present.

    ### 5. Idempotent inventory
    Fetch current sub-issues of the umbrella:
    !`gh api graphql -f query='
      { repository(owner:"w7-mgfcode", name:"ForecastLabAI") {
          issue(number: <N>) {
            subIssues(first: 20) { nodes { number title state } }
          }
      } }'`

    For each epic in the decomposition (except SKIP items):
      a. Search for existing issue by title:
         !`gh issue list --search "<exact epic title>" --json number,title \
           --jq '.[0] | "\(.number // "none") \(.title // "")"'`
         → Record as EXISTS #M / NOT_FOUND
      b. Check if already in the GraphQL subIssues list above → LINKED / UNLINKED

    Print inventory table:
      [phase]   [title-summary]               [exists]     [linked]
      Foundation  E1 foundation ...             ✅ #369      ✅ linked
      Parallel    E2 /flow-brainstorm ...        ✅ #371      ✅/❌ ?
      Parallel    E3 /flow-umbrella ...          ✅ #372      ✅/❌ ?
      Parallel    E4 /flow-epics ...             ✅ #373      ✅/❌ ?
      Release gate  E5 dogfood ...              ⏭️ deferred  —

    ### 6. Create + link loop (write-discipline, per epic not yet linked)
    For each epic where LINKED=false AND phase != SKIP:

      6a. If NOT_FOUND → CREATE the issue:
          Compose body using the epic body template (see § Epic body template).
          Echo dry-run:
            ┌─ DRY-RUN ──────────────────────────────────────────────┐
            │ gh issue create \                                       │
            │   --title "<title>" \                                   │
            │   --body "<body>" \                                     │
            │   --label epic --label flow --label feat \              │
            │   --milestone "flow-pack-suite"                         │
            └────────────────────────────────────────────────────────┘
          APPROVAL GATE: "Type 'approve' to create, anything else to skip."
          If approved: execute gh issue create; capture issue number M from output.
          RATE-DELAY: sleep 1

      6b. Link to umbrella (whether newly created or already existing but UNLINKED):
          Echo dry-run:
            ┌─ DRY-RUN ──────────────────────────────────────────────┐
            │ gh api repos/w7-mgfcode/ForecastLabAI/issues/<N>/sub_issues \│
            │   -X POST -F sub_issue_id=<M> \                        │
            │   --header "GitHub-Next-Preview: true"                  │
            └────────────────────────────────────────────────────────┘
          APPROVAL GATE: "Type 'approve' to link, anything else to skip."
          If approved: execute gh api POST; confirm:
            !`gh issue view <M> --json number,title,labels`
          RATE-DELAY: sleep 1

    ### 7. Verify + gate
    Re-fetch sub-issues via GraphQL (same query as step 5) to confirm final state.
    Print gate result + handoff (see § Output format).

  ── Section F: Epic body template ──
    ## Epic body template

    Use one of these three templates based on phase. Fill <angle-bracket> placeholders.

    FOUNDATION epic:
    ```
    > Sub-issue of #<umbrella_N> (umbrella: <umbrella_title>). Foundation — blocks Epics #<P1>, #<P2>, …

    ## Purpose

    <One-paragraph scope description extracted from the umbrella decomposition line.>

    ## Sub-tasks

    _To be decomposed via `issue-to-subtasks` when this epic is picked up._
    ```

    PARALLEL epic:
    ```
    > Sub-issue of #<umbrella_N> (umbrella: <umbrella_title>). Parallel after Foundation (E1 #<foundation_N>).

    ## Purpose

    <One-paragraph scope description.>

    ## Sub-tasks

    _To be decomposed via `issue-to-subtasks` when this epic is picked up._
    ```

    RELEASE GATE epic:
    ```
    > Sub-issue of #<umbrella_N> (umbrella: <umbrella_title>). Release gate — closes only after Foundation + all Parallel epics close.

    ## Purpose

    <One-paragraph scope description.>

    ## Sub-tasks

    _To be decomposed via `issue-to-subtasks` when this epic is picked up._
    ```

  ── Section G: Output format ──
    ## Output format

    ```
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
      🔗  flow-epics: Epic Decomposition
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    📋 Umbrella #<N> — <title>
      Phase structure: 1 Foundation · M Parallel · 1 Release gate (deferred)

    📋 Epic inventory
      [phase]          [exists]   [linked]
      ✅ #369 E1 Foundation    exists     linked
      ✅ #371 E2 Parallel      exists     ❌ not linked
      ✅ #372 E3 Parallel      exists     ❌ not linked
      ✅ #373 E4 Parallel      exists     ❌ not linked
      ⏭️ E5 Release gate      deferred   —

    📋 Dry-run: writes pending (awaiting approval)
      [dry-run block per epic needing a link]

    📋 Actions taken (after approvals)
      ✅ #371 linked under #<N>
      ✅ #372 linked under #<N>
      ✅ #373 linked under #<N>
      ⏭️ E5 deferred — skipped

    ────────────────────────────────────────────
      ✅ EPICS LINKED — 4/5 epics under #<N> (E5 deferred)
    ────────────────────────────────────────────

    → Next: base_prp:prp-create per open epic:
      - /base_prp:prp-create  (#371 — /flow-brainstorm)
      - /base_prp:prp-create  (#372 — /flow-umbrella)
      (E4 #373 = this PRP, currently executing)
    ```

  ── Section H: Reuse-map (match umbrella-issue.md style) ──
    ## Reuse-map

    | Need | Tool |
    |------|------|
    | Codebase + context priming | core_piv_loop:prime |
    | Epic → 5 executable subtasks | issue-to-subtasks skill |
    | PRP authoring per epic | base_prp:prp-create |
    | Session continuity | writing-session-handoffs |
    | Rules audit | audit-rules-drift |
    | Umbrella creation | /flow-umbrella |


Task 2 — INSTALL .claude/commands/flow/flow-epics.md (local runtime copy):

  REGENERATE as a byte-copy: cp docs/flow-pack/commands/flow-epics.md .claude/commands/flow/

  VERIFY no drift:
    diff -q docs/flow-pack/commands/flow-epics.md .claude/commands/flow/flow-epics.md
    → must produce no output (identical files)

  CONFIRM gitignored:
    git check-ignore .claude/commands/flow/flow-epics.md
    → must print the path (confirms it is ignored and will never appear in git status as tracked)
```

### Integration Points
```yaml
DOCS (tracked — the only committed change):
  - add: docs/flow-pack/commands/flow-epics.md

CLAUDE (local, gitignored — never staged or committed):
  - add: .claude/commands/flow/flow-epics.md

DIRTY WORKTREE (handle carefully):
  - INSPECT before branching: git diff docs/flow-pack/commands/flow-prime.md
  - DO NOT STAGE: uv.lock, docker-compose.lan.yml, docs/flow-pack/commands/flow-prime.md
  - IF flow-prime.md modification is a bug fix relevant to this work, commit it separately first

BRANCH:
  - create off dev: feat/flow-pack-e4-flow-epics
  - verify: git branch --show-current

COMMIT (only when user explicitly authorizes — no auto-commit):
  - format: feat(docs,repo): flow-pack E4 — /flow-epics command template + local install (#373)
  - stage only: docs/flow-pack/commands/flow-epics.md
  - .claude/commands/flow/flow-epics.md is gitignored — it will NOT appear in git status
  - verify pre-commit hook passes: .claude/hooks/check-commit-format.sh

METHODOLOGY DOC (no changes needed):
  - docs/flow-pack-methodology.md already documents /flow-epics fully — do NOT edit it
```

## Validation Loop

### Level 1: File presence + durable-source split
```bash
# tracked source of truth exists and has content
test -f docs/flow-pack/commands/flow-epics.md \
  && wc -l docs/flow-pack/commands/flow-epics.md \
  && echo "OK: tracked file present"

# local install exists
test -f .claude/commands/flow/flow-epics.md && echo "OK: local install present"

# local install is gitignored (CRITICAL — must print the file path, not empty)
git check-ignore .claude/commands/flow/flow-epics.md
# expected output: .claude/commands/flow/flow-epics.md

# local install == tracked template (no drift)
diff -q docs/flow-pack/commands/flow-epics.md .claude/commands/flow/flow-epics.md \
  && echo "OK: no drift between tracked and local"

# only docs/flow-pack/commands/flow-epics.md is a new tracked addition
# .claude/** must NOT appear as staged or tracked
git status --short
# expected: A  docs/flow-pack/commands/flow-epics.md  (and possibly M flow-prime.md unstaged)
```

### Level 2: Fresh-clone recovery reproduction
```bash
# simulate a fresh-clone by removing the local install, then regenerate
rm -f .claude/commands/flow/flow-epics.md
cp docs/flow-pack/commands/*.md .claude/commands/flow/

# verify recovery reproduces the file byte-for-byte
diff -q docs/flow-pack/commands/flow-epics.md .claude/commands/flow/flow-epics.md \
  && echo "OK: recovery reproduces local install"

# both flow-prime and flow-epics should be present after cp
ls .claude/commands/flow/
# expected: flow-epics.md  flow-prime.md
```

### Level 3: Smoke test — dry-run against live umbrella #368
```bash
# In a Claude Code session, invoke:
#   /flow-epics 368
#
# Verify the printed output contains ALL of the following (no gh writes yet):
#   ✅ Inventory table is shown with correct issue numbers for E1–E4
#   ✅ E5 Release gate shown as ⏭️ SKIP (deferred) — NOT created, NOT in dry-run queue
#   ✅ Any UNLINKED epics (E2/E3/E4) shown in the dry-run pending section
#   ✅ Dry-run block echoes the exact gh api POST command with --header "GitHub-Next-Preview: true"
#   ✅ "Type 'approve' to link" gate appears before any write executes
#   ✅ Command ends with "→ Next: base_prp:prp-create" for each open epic
#
# This is interactive verification — no automated assertion.
# After confirming the dry-run, optionally approve the link operations for E2/E3/E4.
```

## Tests / checks required
- [ ] Level 1: file-presence + gitignore + no-drift — all assertions pass.
- [ ] Level 2: recovery reproduces local install from tracked template.
- [ ] Level 3: `/flow-epics 368` dry-run shows correct inventory; E5 shows ⏭️ SKIP.
- [ ] `docs/flow-pack/commands/flow-epics.md` contains provenance HTML comment:
      `grep "provenance:" docs/flow-pack/commands/flow-epics.md`
- [ ] All 8 required sections present in the command spec:
      `grep -E "^## (Objective|Arguments|Process|Epic body template|Output format|Reuse-map)" docs/flow-pack/commands/flow-epics.md | wc -l`
      → must print 6 (+ frontmatter and provenance = 8 total)
- [ ] Sub-issue link command uses `gh api ... --header "GitHub-Next-Preview: true"`:
      `grep "GitHub-Next-Preview" docs/flow-pack/commands/flow-epics.md`
- [ ] Idempotent check uses `--jq '.[0].number // "none"'`:
      `grep '"none"' docs/flow-pack/commands/flow-epics.md`
- [ ] No mention of E2/E3/E5 implementation logic in flow-epics.md — E5 is only shown as SKIP.
- [ ] Standard repo gates unaffected (markdown-only change):
      `uv run ruff check . && uv run mypy app/ && uv run pytest -v -m "not integration"`
      → all must be green (unchanged by this PRP)

## Final Validation Checklist
- [ ] 2 files created: `docs/flow-pack/commands/flow-epics.md` (tracked) and
      `.claude/commands/flow/flow-epics.md` (local, gitignored).
- [ ] Durable-source split holds: docs tracked, .claude ignored + regenerable from `cp`.
- [ ] Command spec is self-contained: an agent reading only `docs/flow-pack/commands/flow-epics.md`
      and codebase can implement `/flow-epics` correctly without additional context.
- [ ] All write-discipline invariants encoded in the Process section:
      dry-run echo → idempotent check → approval gate → rate-delay → confirm.
- [ ] Sub-issue REST API used correctly:
      `gh api ... -X POST -F sub_issue_id=N --header "GitHub-Next-Preview: true"` for writes,
      GraphQL for reads.
- [ ] E5 Release gate hard-coded as ⏭️ SKIP (never auto-created).
- [ ] E2/E3 behavior not included in flow-epics.md.
- [ ] Branch is `feat/flow-pack-e4-flow-epics` off `dev`; commit references `(#373)`.
- [ ] No commit/push performed by this PRP execution unless explicitly requested by the user.
- [ ] `uv.lock` + `docker-compose.lan.yml` + unstaged `flow-prime.md` left untouched.
- [ ] Provenance header present in `docs/flow-pack/commands/flow-epics.md`.

## Anti-Patterns to Avoid
- ❌ Using `gh` CLI native sub-issue support or any undocumented extension — `gh api POST` directly.
- ❌ Omitting `--header "GitHub-Next-Preview: true"` from the sub-issue POST call.
- ❌ Skipping the dry-run echo before any `gh` write.
- ❌ Auto-proceeding after dry-run without waiting for "approve".
- ❌ Auto-creating E5 (Release gate) — explicitly deferred per #373 scope.
- ❌ Writing app/backend/frontend code (this is a docs-only PRP).
- ❌ Staging `uv.lock` / `docker-compose.lan.yml` / `flow-prime.md`.
- ❌ Treating `.claude/commands/flow/flow-epics.md` as the committed source of truth.
- ❌ Letting the local install drift from the tracked template after writing.
- ❌ Implementing E2 (/flow-brainstorm) or E3 (/flow-umbrella) behavior here.

---

## Confidence Score: 7/10

One-pass likelihood is moderate-to-high: methodology is fully documented, `gh api` patterns are
verified in the umbrella rule and methodology doc, and this is markdown-only (no runtime/type
risk). −3 for:

1. **Decomposition parser complexity** — the umbrella body uses varied text patterns (bold labels,
   embedded `#N` refs, "(deferred)" markers, "not yet created" prose); the implementing agent
   must handle all variants without getting any text extraction subtly wrong.
2. **Two-phase idempotency** — `exists?` + `linked?` are independent checks that must compose
   correctly (four states: exists+linked, exists+unlinked, not-exists, deferred). Getting one
   case wrong silently skips a link or attempts a duplicate create.
3. **Authoring a ~150-line markdown spec** — the command file is long and the implementing agent
   must maintain section ordering, template exactness (epic blockquote wording), and style
   consistency with `flow-prime.md` throughout.
