---
description: Create phase-ordered epic issues from an umbrella decomposition, link via REST sub-issues API, and hand off to base_prp:prp-create per epic
---

<!-- provenance: docs/flow-pack-methodology.md §"/flow-epics — epic issues" + §"Epic contract"
     + §"Hierarchy-as-data (REST API)". Source of truth for .claude/commands/flow/flow-epics.md.
     Recovery: cp docs/flow-pack/commands/flow-epics.md .claude/commands/flow/flow-epics.md
     Full methodology: docs/flow-pack-methodology.md -->

# flow-epics: Epic Decomposition

## Objective

Read the umbrella issue's Decomposition section, create N phase-ordered epic issues
(Foundation → Parallel → Release gate) with idempotent guards, link each as a sub-issue of
the umbrella via the GitHub REST API, and hand off to `base_prp:prp-create` per open epic.
Skips epics that already exist and/or are already linked.

## Arguments

`$ARGUMENTS` — umbrella issue number (e.g. `368` or `#368`). Required.
If omitted, reads the active umbrella number from the "In-progress issues" block in
`.flow/state.md` (looks for the `[umbrella,flow]`-labeled entry).

## Process

### 1. Parse argument

Strip `#` prefix from `$ARGUMENTS` if present. Use the result as the umbrella issue number.

If empty, read the umbrella number from the you-are-here snapshot:

!`cat .flow/state.md | grep "umbrella,flow" | head -1`

Abort with ❌ if no umbrella number can be resolved.

### 2. Fetch umbrella

!`gh issue view <N> --json number,title,body,labels,milestone`

Abort with ❌ if:
- The issue is not found.
- The `umbrella` label is absent from the labels list.

Capture: `umbrella_title`, `body`, `labels[]`, `milestone.title`.

### 3. Extract decomposition

Parse the body: find lines between the `## Decomposition` heading and the next `##` heading.

For each bullet line:
- Detect phase marker from bold text: `**Foundation**` / `**Parallel**` / `**Release gate**`
- Extract scope description (used to construct epic title + Purpose body paragraph)
- Detect any embedded `#N` ref in the line (pre-existing issue pointer — use as EXISTS hint)
- Flag as `SKIP` if the line contains `(deferred)` OR if the phase is Release gate AND the
  scope mentions "not yet created" or "deferred"

**Epic title pattern** — must match existing issues exactly for idempotent search:

```
feat(<scope>): flow-pack <phase-label> — <scope description>
```

Example from live epics: `"feat(repo): flow-pack E1 — foundation (/flow-prime + tracked contract + rule + labels/milestone)"`

### 4. Pre-flight checks

Verify required labels exist. Use `--paginate` — repos with >30 labels require it and `gh label list`
truncates at 30 without `--paginate`, silently missing labels created later:

!`gh api repos/{owner}/{repo}/labels --paginate --jq '.[].name' | grep -E "^(epic|flow|feat)$" | wc -l`

Abort with ❌ if result is not `3` (one or more labels missing — create before retrying).

Verify milestone exists:

!`gh api repos/{owner}/{repo}/milestones --jq '[.[].title] | contains(["flow-pack-suite"])'`

Abort with ❌ if `false`.

Compute epic label set: take umbrella labels → remove `"umbrella"` → add `"epic"`. For umbrella
`#368` (labels: `umbrella`, `flow`) → epic labels: `epic`, `flow`, `feat`.

### 5. Idempotent inventory

Fetch current sub-issues of the umbrella via GraphQL:

!`gh api graphql -f query='
  { repository(owner:"w7-mgfcode", name:"ForecastLabAI") {
      issue(number: <N>) {
        subIssues(first: 20) { nodes { number title state } }
      }
  } }'`

For each epic in the decomposition (except SKIP items):

**a. Search for existing issue by exact title:**

!`gh issue list --search "<exact epic title>" --json number,title \
  --jq '.[0] | "\(.number // "none") \(.title // "")"'`

→ Record as `EXISTS #M` / `NOT_FOUND`. Verify the returned title matches character-for-character
(GitHub search is fuzzy — reject partial matches).

**b. Check GraphQL sub-issues list:** If `#M` appears in `subIssues.nodes` → `LINKED`. Otherwise → `UNLINKED`.

Print inventory table before any writes:

```
┌──────────────────────────────────────────────────────────────────────┐
│  Phase          Title summary                  Exists    Linked      │
│  Foundation     E1 — foundation                ✅ #369   ✅ linked   │
│  Parallel       E2 — /flow-brainstorm          ✅ #371   ❌ unlinked │
│  Parallel       E3 — /flow-umbrella            ✅ #372   ❌ unlinked │
│  Parallel       E4 — /flow-epics               ✅ #373   ❌ unlinked │
│  Release gate   E5 — dogfood + portability     ⏭️ defer  —          │
└──────────────────────────────────────────────────────────────────────┘
```

### 6. Create + link loop

For each epic where `LINKED=false` AND phase is NOT `SKIP`:

**6a. If `NOT_FOUND` → CREATE the issue:**

Compose body using the epic body template (§ Epic body template below).

Echo dry-run:

```
┌─ DRY-RUN ───────────────────────────────────────────────────────────┐
│ gh issue create \                                                    │
│   --title "<exact epic title>" \                                    │
│   --body "<body from template>" \                                   │
│   --label epic --label flow --label feat \                          │
│   --milestone "flow-pack-suite"                                     │
└─────────────────────────────────────────────────────────────────────┘
```

APPROVAL GATE: "Type 'approve' to create, anything else to skip."

If approved: execute `gh issue create`; capture the returned issue number as `M`.

RATE-DELAY: `sleep 1`

**6b. Link to umbrella** (whether newly created or already `EXISTS` but `UNLINKED`):

Echo dry-run:

```
┌─ DRY-RUN ───────────────────────────────────────────────────────────┐
│ gh api repos/w7-mgfcode/ForecastLabAI/issues/<N>/sub_issues \       │
│   -X POST -F sub_issue_id=<M> \                                     │
│   --header "GitHub-Next-Preview: true"                              │
└─────────────────────────────────────────────────────────────────────┘
```

APPROVAL GATE: "Type 'approve' to link, anything else to skip."

If approved: execute `gh api POST`. Confirm:

!`gh issue view <M> --json number,title,labels`

RATE-DELAY: `sleep 1`

### 7. Verify + gate

Re-fetch sub-issues via GraphQL (same query as step 5) to confirm final state.

Count linked epics (excluding SKIP items). Print gate result and per-epic handoff.

## Epic body template

Use the template matching the epic's phase. Fill `<angle-bracket>` placeholders.

**FOUNDATION epic:**

```
> Sub-issue of #<umbrella_N> (umbrella: <umbrella_title>). Foundation — blocks Epics #<P1>, #<P2>, …

## Purpose

<One-paragraph scope description extracted from the umbrella decomposition line.>

## Sub-tasks

_To be decomposed via `issue-to-subtasks` when this epic is picked up._
```

**PARALLEL epic:**

```
> Sub-issue of #<umbrella_N> (umbrella: <umbrella_title>). Parallel after Foundation (E1 #<foundation_N>).

## Purpose

<One-paragraph scope description extracted from the umbrella decomposition line.>

## Sub-tasks

_To be decomposed via `issue-to-subtasks` when this epic is picked up._
```

**RELEASE GATE epic:**

```
> Sub-issue of #<umbrella_N> (umbrella: <umbrella_title>). Release gate — closes only after Foundation + all Parallel epics close.

## Purpose

<One-paragraph scope description extracted from the umbrella decomposition line.>

## Sub-tasks

_To be decomposed via `issue-to-subtasks` when this epic is picked up._
```

## Output format

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  🔗  flow-epics: Epic Decomposition
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 Umbrella #<N> — <title>
  Phase structure: 1 Foundation · M Parallel · 1 Release gate (deferred)

📋 Epic inventory
  [phase]              [exists]      [linked]
  ✅ #369 E1 Foundation   exists       linked
  ✅ #371 E2 Parallel     exists       ❌ not linked
  ✅ #372 E3 Parallel     exists       ❌ not linked
  ✅ #373 E4 Parallel     exists       ❌ not linked
  ⏭️ E5 Release gate      deferred     —

📋 Dry-run: writes pending (awaiting approval)
  [dry-run block per epic needing a link or create]

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

## Reuse-map

| Need | Tool |
|------|------|
| Codebase + context priming | `core_piv_loop:prime` |
| Epic → 5 executable subtasks | `issue-to-subtasks` skill |
| PRP authoring per epic | `base_prp:prp-create` |
| Session continuity | `writing-session-handoffs` |
| Rules audit | `audit-rules-drift` |
| Umbrella creation | `/flow-umbrella` |
