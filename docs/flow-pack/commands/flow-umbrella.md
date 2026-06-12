---
description: Generate and create umbrella GitHub issue from V2 ship list
---

<!-- provenance: flow-pack methodology stage 2 (umbrella issue creation).
     Source of truth: docs/flow-pack/commands/flow-umbrella.md (tracked).
     Local install:   .claude/commands/flow/flow-umbrella.md (gitignored, regenerable from this file).
     Recovery: cp docs/flow-pack/commands/flow-umbrella.md .claude/commands/flow/flow-umbrella.md
     Full methodology: docs/flow-pack-methodology.md (§ Stage 2 — Decompose)
     Agent contract:   .claude/rules/umbrella-issue.md -->

# flow-umbrella: Umbrella Issue Creation

## Objective

Transform the approved V2 ship list (from `/flow-brainstorm`) into a GitHub umbrella issue with
the **7-field body contract** (`umbrella-issue.md`). The umbrella becomes the root of the GitHub
issue hierarchy that `/flow-epics` populates with child epic issues.

**DELEGATION: approval gate required before any GitHub write.**
Steps 1–5 are read-only. Step 6 blocks on explicit human approval. No issue is created until
the user types "approve."

## Process

### 1. Read context

Load the working-state files produced by `/flow-prime` and `/flow-brainstorm`:

!`cat .flow/brainstorm-log.md`

!`cat .flow/state.md`

Extract:
- **Initiative title** — from `$ARGUMENTS` if provided; otherwise the initiative title from the
  V2 ship list header in `.flow/brainstorm-log.md` (or the `In-progress` line in the
  `FLOW-PRIME:YOU-ARE-HERE` block of `.flow/state.md`).
- **V2 ship items** — the approved set from the `/flow-brainstorm` output (`## V2 ship list`
  section).
- **Defer items + reasons** — items from the defer list; each needs a written one-clause reason
  for the Out-of-scope section.
- **Milestone name** — from the `FLOW-PRIME:YOU-ARE-HERE` marker block (`Active milestone:` line).
- **Type label** — first token before `(` in a conventional-commit title
  (`feat(repo): …` → `feat`); default `feat` if the title is not in conventional-commit format.

**Missing brainstorm log:** if `.flow/brainstorm-log.md` is absent or has no `## V2 ship list`
section, print:
```
ERROR: No V2 ship list found in .flow/brainstorm-log.md.
Run /flow-brainstorm first, then re-run /flow-umbrella.
```
and stop.

### 2. Validate prerequisites

Check that all required labels and the active milestone exist in the repo:

!`gh label list --json name --jq '[.[].name] | sort | join(", ")'`

!`gh api repos/{owner}/{repo}/milestones --jq '.[] | select(.state=="open") | .title'`

Required labels: `umbrella`, `flow`, and the type label (e.g., `feat`).

If any label or milestone is **missing**, print the exact remediation commands and **stop** — do
not proceed to draft until all prerequisites are satisfied:
```bash
# Create missing labels (run only the ones that are absent)
gh label create umbrella --color "0052CC" --description "Multi-week initiative scope owner"
gh label create flow     --color "BFD4F2" --description "Managed by the flow: command suite"
gh label create epic     --color "1D76DB" --description "Delivery surface within an umbrella"

# Create missing milestone
gh api repos/{owner}/{repo}/milestones -X POST \
  -F title="<milestone-name>" -F state="open"
```

### 3. Idempotency check

Search for an open issue with the same title before drafting:

```bash
gh issue list --state open \
  --search "<proposed issue title>" \
  --json number,title \
  --jq '.[0] // empty'
```

If an open issue with the same title exists:
- Print: `Umbrella #N already exists: <url> — skipping create.`
- Jump to step 9 with the existing number `N`.

Note: a **closed** umbrella with the same title does NOT block creation — a closed umbrella means
the initiative is complete; a new one with the same name may legitimately start.

### 4. Draft the 7-field body

Synthesize from the context loaded in step 1. **All 7 sections are required** — a body missing
any section is not done (invariant from `umbrella-issue.md`). Use the exact section headings
below:

```markdown
## Summary
<One paragraph: what is wrong or missing in the current state. Cite baseline artifacts
(branch, existing files, gap). Describe the problem only — not the solution.>

## Approach
<One paragraph: architectural delta only. No new services, no new routers, no new runtime
dependencies unless explicitly justified. State what will NOT change. Reference the
durable-source split if the command-file pattern is involved.>

## Decomposition
<Phase taxonomy — exactly ONE Foundation (blocks all), N Parallel (run concurrently after
Foundation), exactly ONE Release gate (closes ONLY after Foundation + all Parallel).
Epics do not exist yet — use "not yet created" suffixes; never invent fake issue numbers.>

- [ ] **E1 — Foundation** (blocks E2–EN): <one-line description> — not yet created
- [ ] **E2 — Parallel**: <one-line description> — not yet created
- [ ] **EN — Release gate** (closes after Foundation + all Parallel): <description> — not yet created

## Out of scope (explicit)
<Items from the defer list and any scope boundary.
Every line MUST end with " — reason: <one sentence>".
A blank reason is a process failure (invariant: every defer has a reason).>

- <item> — reason: <one sentence>

## Success criteria
<Checkbox list. Each criterion must be independently verifiable by an outside reviewer.
Specific and measurable — not "everything works".>

- [ ] <specific, measurable outcome>

## Risks
| Risk | Mitigation |
|------|------------|
| <risk> | <mitigation> |

## Tracking
- Source of truth: `docs/flow-pack-methodology.md` + working state `.flow/state.md`
- Milestone: <milestone name>
- **One-pass confidence: X/10** (<one-sentence rationale>)
```

### 5. Dry-run echo

Print the **exact commands to be executed** — **do not run them yet**:

```bash
cat > /tmp/umbrella-body.md << 'BODY_EOF'
[full 7-field body — show every line exactly as it will be submitted]
BODY_EOF

gh issue create \
  --title "<initiative title>" \
  --body-file /tmp/umbrella-body.md \
  --label "umbrella" --label "flow" --label "<type>" \
  --milestone "<milestone-name>"
```

> **Why `--body-file`:** multi-line markdown bodies containing backticks, code fences, and pipe
> characters cause shell quoting failures with `--body "..."`. The `--body-file` approach is
> required for umbrella bodies (available since `gh` v1.x).

### 6. Approval gate

Print:
```
────────────────────────────────────────────
Awaiting approval. Type 'approve' to create the umbrella issue.
Any other response = abort (no write).
────────────────────────────────────────────
```

Wait for user input.
- **"approve"** (case-insensitive) → proceed to step 7.
- **Anything else** → print `Aborted — no issue created.` and stop.

### 7. Execute

Create the umbrella issue using `--body-file` for safe multi-line body handling:

```bash
cat > /tmp/umbrella-body.md << 'BODY_EOF'
[7-field body]
BODY_EOF

gh issue create \
  --title "<initiative title>" \
  --body-file /tmp/umbrella-body.md \
  --label "umbrella" --label "flow" --label "<type>" \
  --milestone "<milestone-name>"
```

Capture the output URL. Extract issue number `N` from the URL
(e.g., `https://github.com/…/issues/42` → `N=42`).

### 8. Confirm

Verify labels and milestone were attached:

```bash
gh issue view <N> --json number,title,labels,milestone \
  --jq '"#\(.number): \(.title) [\(.labels | map(.name) | join(","))] milestone=\(.milestone.title // "none")"'
```

If any label or milestone is missing, print the remediation commands:
```bash
gh issue edit <N> --add-label <missing-label>
gh issue edit <N> --milestone "<milestone-name>"
```

### 9. Gate and next-command

Gate is ✅ **UMBRELLA CREATED** when:
- Issue number `N` returned from step 7.
- All 7 body sections present.
- Labels `umbrella`, `flow`, and the type label attached.
- Milestone attached.

Gate is ❌ **FAILED** when:
- `gh issue create` returned non-zero, OR
- Confirm step shows missing labels or milestone (and remediation was not applied).

Print the gate result, then the next-command pointer regardless of outcome:

```
→ Next: /flow-epics #<N>
```

## Output Format

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  🏗️  flow-umbrella: Umbrella Issue
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 Context
  V2 ship items: N  |  Defer items: M
  Initiative: <title>
  Milestone: <name>  |  Labels: umbrella ✅ flow ✅ <type> ✅

📋 Prerequisite check
  umbrella label: [✅/❌]  |  flow label: [✅/❌]  |  <type> label: [✅/❌]
  Milestone <name>: [✅/❌]  |  Existing umbrella: [#N / none]

📋 Dry-run
  cat > /tmp/umbrella-body.md << 'BODY_EOF'
  [full 7-field body]
  BODY_EOF
  gh issue create --title "..." --body-file /tmp/umbrella-body.md --label ... --milestone ...

────────────────────────────────────────────
  Awaiting approval. Type "approve" to create.
────────────────────────────────────────────

[After approval:]

📋 Created
  ✅ gh issue create → #N: <title>
  Labels: umbrella, flow, <type>  |  Milestone: <name>

────────────────────────────────────────────
  [✅/❌] UMBRELLA CREATED → #N
────────────────────────────────────────────

→ Next: /flow-epics #N
```

## Arguments

`$ARGUMENTS` — optional initiative description. Overrides the title extracted from
`.flow/brainstorm-log.md`. Example: `/flow-umbrella integrate flow-pack as the flow: command suite`.
If omitted, the initiative title is derived from the V2 ship list header in the brainstorm log.
