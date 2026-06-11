name: "PRP — flow-pack E3 (/flow-umbrella: rule-driven umbrella issue creation)"
description: |
  E3 parallel epic of the flow: command-suite integration. Lands the tracked
  docs/flow-pack/commands/flow-umbrella.md template + the local .claude runtime install.
  The command generates a 7-field umbrella body from the approved V2 ship list, echoes a
  dry-run, waits for approval, and creates the umbrella GitHub issue. Parallel with E2/E4;
  depends only on E1 (foundation/labels/milestone) being merged.

<!-- provenance:
  Methodology: docs/flow-pack-methodology.md (§ Stage 2 — Decompose, § Umbrella contract)
  Rule source: .claude/rules/umbrella-issue.md
  E1 pattern:  PRPs/PRP-flow-pack-E1-foundation.md  ← mirror this PRP's structure exactly
  Command pattern: docs/flow-pack/commands/flow-prime.md ← mirror this command's style
  Live umbrella example: gh issue view 368 (7-field body verified in .flow/state.md)
  Working analysis: .flow/state.md (Phase 4) + .flow/brainstorm-log.md (Round 2) -->

## Issue links
- Umbrella: **#368** — feat(repo): integrate flow-pack methodology as the flow: command suite
- This epic: **#372** — flow-pack E3 — /flow-umbrella (7-field umbrella body, approval-gated write)
- Milestone: **#1 flow-pack-suite** · labels: `epic`, `flow`
- Depends on: **E1 #369** (merged via PR #370) — labels/milestone/tracked-docs foundation

---

## Goal

Implement the **E3 /flow-umbrella command**: the tracked template plus its local runtime install
that generates and creates a GitHub umbrella issue from the approved V2 ship list. The end state:
a user runs `/flow-umbrella <initiative>` (after `/flow-brainstorm` has produced a V2 list),
inspects the dry-run echo of the full 7-field body, types "approve," and the umbrella issue is
created with `umbrella` + `flow` + type labels and the active milestone attached.

**Deliverable:** 2 files (tracked template + local runtime install). No epic creation. No
milestone/label creation (must exist from E1). No commit/push. Parallel with E2 (#371) and E4
(#373).

## Why

- The flow: suite's Stage 2 ("Decompose") has no umbrella-creation command yet.
  `/flow-brainstorm` produces a V2 ship list but has nowhere to hand it off.
- E3 fills that gap: it wires the approved V2 list into the 7-field umbrella contract
  (`umbrella-issue.md`) and materializes it as a GitHub issue that `/flow-epics` can then
  decompose into child epics.
- The durable-source split (`.claude/` gitignored) requires a tracked template. Without E3's
  `docs/flow-pack/commands/flow-umbrella.md`, a fresh clone loses the command.

## What

A docs-first delivery: tracked command template → byte-copy local install → working `/flow-umbrella`.

### Success Criteria
- [ ] `docs/flow-pack/commands/flow-umbrella.md` exists (tracked canonical spec/template).
- [ ] `.claude/commands/flow/flow-umbrella.md` present, byte-identical to the tracked template
      (confirmed by `diff -q`).
- [ ] `git check-ignore .claude/commands/flow/flow-umbrella.md` prints the path (confirms it's
      gitignored — not the durable artifact).
- [ ] Fresh-clone recovery works: `cp docs/flow-pack/commands/*.md .claude/commands/flow/`
      reproduces the local command.
- [ ] `/flow-umbrella` validates prerequisites (labels/milestone) before drafting.
- [ ] `/flow-umbrella` performs idempotency check before dry-run.
- [ ] `/flow-umbrella` dry-run echoes the full `gh issue create` command + body before any write.
- [ ] `/flow-umbrella` approval gate prevents write on any response other than "approve."
- [ ] The created umbrella issue carries all 7 required sections, labels `umbrella`+`flow`+type,
      and the active milestone.
- [ ] Every created artifact carries a provenance header linking to its source.
- [ ] E2/E4/E5 NOT implemented here. No epic creation, no sub-issue linking.

---

## All Needed Context

### Documentation & References
```yaml
# THE PATTERN TO MIRROR — read these before writing anything
- file: PRPs/PRP-flow-pack-E1-foundation.md
  why: The E3 PRP's sibling; mirror its exact PRP structure. This implementation follows the
       same two-file pattern (tracked template + local install). Read every section heading.

- file: docs/flow-pack/commands/flow-prime.md
  why: The only existing flow: command. Mirror its file structure exactly:
       frontmatter YAML (description:) → provenance HTML comment → # Title → ## Objective →
       ## Process (numbered steps with bash blocks) → ## Output Format (fenced block) →
       ## Arguments ($ARGUMENTS line). flow-umbrella.md must follow this layout.

- file: docs/flow-pack-methodology.md
  sections:
    - "## Stage 2 — Decompose — /flow-umbrella" (steps 1–4 + next-pointer spec)
    - "## Umbrella contract (7-field body)" (exact field names + content rules)
    - "## Durable-source split" (table: tracked vs local vs purpose)
    - "## Fresh-clone recovery" (the cp command + diff check)
  why: The authoritative spec for what /flow-umbrella does and the 7-field contract.

- file: .claude/rules/umbrella-issue.md
  sections:
    - "## Umbrella body — 7-field contract" (field table with rules)
    - "## Write discipline" (dry-run echo / idempotent check / approval gate / rate-delay)
    - "## Labels and milestone" (required labels + milestone policy)
    - "## Source-of-truth split (CRITICAL)" (the durable vs local split + recovery)
  why: The agent contract for umbrella creation; flow-umbrella.md must implement every clause.

# LIVE UMBRELLA EXAMPLE (for 7-field body reference)
- bash: "gh issue view 368 --json body --jq '.body'"
  why: A real 7-field umbrella body created for this exact project. Use as a reference for
       tone, section depth, and the "not yet created" placeholder pattern in Decomposition.

# WORKING STATE
- file: .flow/brainstorm-log.md
  why: Contains the V2 ship list, defer list with reasons, and the 5-dim scores that
       /flow-umbrella reads to synthesize the 7-field body. Shows V2 items that became
       the E1–E5 epics of #368.

- file: .flow/state.md
  sections: "FLOW-PRIME:YOU-ARE-HERE" marker block
  why: Contains the active milestone name, label status, and current branch/version that
       /flow-umbrella uses to validate prerequisites.

# HAND-OFF SPEC
- file: docs/flow-pack-methodology.md
  section: "## Stage 3 — Execute (delegated)" and the FLAI mapping table rows for
           "Umbrella issue creation (01)" and "Epic creation + linking (01)"
  why: Confirms /flow-umbrella ends with "→ Next: /flow-epics #N" and that epic creation
       belongs entirely to /flow-epics (E4 #373). Do not blur the boundary.
```

### Current Codebase tree (relevant slice)
```bash
docs/
  flow-pack-methodology.md              # ✅ tracked; § Stage 2 = /flow-umbrella spec
  flow-pack/
    commands/
      flow-prime.md                     # ✅ tracked; MIRROR this structure
      # flow-umbrella.md does NOT exist yet — to create
.claude/
  commands/flow/
    flow-prime.md                       # ✅ local install (gitignored); byte-copy of tracked
    # flow-umbrella.md does NOT exist yet — to create
  rules/
    umbrella-issue.md                   # ✅ local rule; contains 7-field contract + write discipline
.flow/
  state.md                              # working state; has You-Are-Here with milestone/labels
  brainstorm-log.md                     # V2 ship list + defer list
PRPs/
  PRP-flow-pack-E1-foundation.md        # ✅ the sibling PRP — mirror its layout
  PRP-flow-pack-E3-flow-umbrella.md     # this PRP
```

### Desired Codebase tree (files to add + responsibility)
```bash
docs/
  flow-pack/
    commands/
      flow-umbrella.md    # TRACKED durable template/spec for /flow-umbrella
                          # Contains: frontmatter, provenance, full 9-step process,
                          # output format, $ARGUMENTS spec.
                          # Source of truth for the command.
.claude/
  commands/flow/
    flow-umbrella.md      # LOCAL install — byte-copy of the tracked template (gitignored).
                          # Claude Code reads this when the user types /flow-umbrella.
                          # Recovery: cp docs/flow-pack/commands/flow-umbrella.md .claude/commands/flow/
```

### Known Gotchas & Quirks
```text
# CRITICAL: .claude/ is gitignored (confirmed: /.claude and .claude in .gitignore).
#   The local command at .claude/commands/flow/flow-umbrella.md is NEVER the durable
#   artifact. Durable truth = docs/flow-pack/commands/flow-umbrella.md. The same
#   gitignore split from E1 applies here — never treat the local copy as the source of truth.

# CRITICAL: Local install must be byte-identical to tracked template. Verify:
#   diff -q docs/flow-pack/commands/flow-umbrella.md \
#           .claude/commands/flow/flow-umbrella.md && echo "OK no drift"
#   If they drift, the tracked template wins. Recovery = cp.

# CRITICAL: The 7-field body must contain ALL 7 sections with their exact headings:
#   ## Summary / ## Approach / ## Decomposition / ## Out of scope (explicit) /
#   ## Success criteria / ## Risks / ## Tracking
#   A body missing any section = not done (umbrella-issue.md invariant).

# CRITICAL: Write discipline order — the command MUST do these in sequence:
#   1. prerequisites check (labels + milestone exist)  ← fail fast before any draft
#   2. idempotency check (existing issue title search) ← skip create if already exists
#   3. draft 7-field body
#   4. dry-run echo (full body + gh command)
#   5. approval gate (block on user input)
#   6. execute gh issue create (only on "approve")
#   7. confirm (gh issue view)
#   8. print gate + next pointer
#   Never swap 1 and 2. Never skip 4 or 5.

# CRITICAL: gh issue create --body with multi-line content.
#   Use --body-file <tempfile> (NOT --body "...") to avoid shell quoting issues
#   with multi-line markdown bodies. Pattern:
#     cat > /tmp/umbrella-body.md << 'BODY_EOF'
#     [body content]
#     BODY_EOF
#     gh issue create --title "..." --body-file /tmp/umbrella-body.md --label ... --milestone ...
#   gh CLI --body-file has been available since gh v1.x; verified against E1 groundwork.

# CRITICAL: Type label derivation.
#   The title follows conventional-commit format: "feat(repo): <initiative>".
#   The type label is the first token before "(" — default "feat" if ambiguous.
#   The type label must exist in the repo (e.g., gh label list | grep feat).
#   Umbrella-issue.md says: "Labels ⊇ umbrella label set (plus the `epic` label)" for epics,
#   but for the UMBRELLA issue itself: umbrella + flow + type label.

# GOTCHA: Decomposition section — epic #N refs.
#   When /flow-umbrella runs, epic issues don't exist yet. Use PROPOSED descriptions
#   with "(not yet created)" suffixes. Pattern from live #368:
#     - [ ] **E1 — Foundation** (blocks all): <description> — not yet created
#     - [ ] **E2 — Parallel**: <description> — not yet created
#   Do NOT put fake "#N" refs for unborn issues. /flow-epics will assign real numbers.

# GOTCHA: Idempotency check searches open issues only (--state open).
#   A closed umbrella with the same title won't block creation. This is intentional:
#   a closed umbrella = finished initiative; a new one may legitimately start.

# GOTCHA: Milestone name matching in gh CLI.
#   gh issue create --milestone "<name>" requires the EXACT milestone title string
#   (case-sensitive). Always read the milestone name from .flow/state.md You-Are-Here
#   or from `gh api repos/{owner}/{repo}/milestones --jq '.[0].title'` rather than
#   hard-coding it.

# GOTCHA: commit-format.md requires every commit to reference an open issue.
#   If a commit is needed (authorized by user), reference #372 — that's E3's issue.
#   Branch = feat/flow-pack-e3-flow-umbrella. But NO commit/push happens in this PRP.

# SCOPE: Do NOT create flow-brainstorm, flow-epics, or any other command here.
#   E3 ships /flow-umbrella only. E2 (#371) and E4 (#373) are separate parallel epics.
#   E5 is the release gate and remains deferred.
```

---

## Implementation Blueprint

### list of tasks (dependency order)
```yaml
Task 1 — CREATE docs/flow-pack/commands/flow-umbrella.md (tracked canonical template):
  - MIRROR structure of: docs/flow-pack/commands/flow-prime.md
    (frontmatter YAML → provenance HTML comment → # Title → ## Objective → ## Process
    (9 numbered steps, bash blocks) → ## Output Format (fenced block) → ## Arguments)
  - INCLUDE frontmatter: "description: Generate and create umbrella GitHub issue from V2 ship list"
  - INCLUDE provenance header naming: docs/flow-pack-methodology.md (§ Stage 2), umbrella-issue.md
  - SPEC the 9-step process (see § Per-task notes below for full content)
  - INCLUDE the output format block (gate + next-command pointer)
  - INCLUDE "$ARGUMENTS" line (initiative description; derived from brainstorm log if omitted)
  - HEADER: provenance comment → docs/flow-pack-methodology.md, .claude/rules/umbrella-issue.md

Task 2 — INSTALL .claude/commands/flow/flow-umbrella.md (local runtime copy):
  - GENERATE as a byte-copy:
      cp docs/flow-pack/commands/flow-umbrella.md .claude/commands/flow/flow-umbrella.md
  - VERIFY no drift:
      diff -q docs/flow-pack/commands/flow-umbrella.md .claude/commands/flow/flow-umbrella.md
        && echo "OK no drift"
  - DO NOT hand-edit the local copy — copy only.

Task 3 — VERIFY the durable-source split:
  - git check-ignore .claude/commands/flow/flow-umbrella.md   (must print the path)
  - diff -q docs/flow-pack/commands/flow-umbrella.md .claude/commands/flow/flow-umbrella.md
  - git status --short   (only docs/flow-pack/commands/flow-umbrella.md should be a new tracked file)
  - Confirm .claude/commands/flow/flow-umbrella.md is NOT staged.

Task 4 — VERIFY fresh-clone recovery (optional, proves robustness):
  - Simulate: rm -f .claude/commands/flow/flow-umbrella.md
  - Regenerate: cp docs/flow-pack/commands/*.md .claude/commands/flow/
  - Confirm: diff -q docs/flow-pack/commands/flow-umbrella.md .claude/commands/flow/flow-umbrella.md
```

### Per-task notes — full /flow-umbrella command content spec

**Task 1 is the high-value task.** The command file must contain the following process, verbatim
or faithful to this spec. Each step maps to a clause in `umbrella-issue.md` § Write discipline.

```text
## Process

### 1. Read context
  - Load .flow/brainstorm-log.md: extract V2 ship list, defer list (with reasons), initiative title.
  - Load .flow/state.md FLOW-PRIME:YOU-ARE-HERE block: extract milestone name, type label, branch.
  - $ARGUMENTS overrides the initiative description if provided.
  - If .flow/brainstorm-log.md is missing or has no V2 section, print:
      "ERROR: No V2 ship list found. Run /flow-brainstorm first, then re-run /flow-umbrella."
    and stop.

### 2. Validate prerequisites
  Commands to run:
    gh label list --json name --jq '[.[].name]'    # check for umbrella, flow, <type>
    gh api repos/{owner}/{repo}/milestones \
      --jq '.[] | select(.state=="open") | .title'  # check milestone exists
  If any required label or milestone is missing:
    print the exact gh label create / gh milestone create commands to remediate.
    STOP — do not proceed to draft.

### 3. Idempotency check
  Command:
    gh issue list --state open \
      --search "<proposed issue title>" \
      --json number,title \
      --jq '.[0] // empty'
  If an open issue with the same title exists:
    print "Umbrella #N already exists: <url> — skipping create."
    jump to step 8 (print gate + next-pointer with the existing number).

### 4. Draft the 7-field body
  Synthesize from context (step 1). ALL 7 sections required:

  ## Summary
  <One paragraph: what is wrong/missing in the current state. Cite baseline artifacts
  (e.g., "ForecastLabAI has X but lacks Y …"). Do not describe the solution here.>

  ## Approach
  <One paragraph: architectural delta only. No new runtime deps, no new services, no new
  routers unless justified. Describe the shape of the change ("thin commands that delegate
  to existing primitives …").>

  ## Decomposition
  Phase taxonomy (invariant from docs/flow-pack-methodology.md § Invariants):
    - Exactly ONE Foundation epic (blocks all others)
    - N Parallel epics (run concurrently after Foundation)
    - Exactly ONE Release-gate epic (closes ONLY after Foundation + all Parallel)
  Format per entry:
    - [ ] **EN — <Phase>** (<phase-note>): <one-line description> — not yet created
  Use "not yet created" because /flow-epics hasn't run. Do NOT invent fake #N refs.

  ## Out of scope (explicit)
  <Every item from the defer list + any scope boundary.>
  Each line must end with " — reason: <one sentence>".
  Never leave a blank reason (umbrella-issue.md invariant: every defer has a reason).

  ## Success criteria
  Checkbox list. Each criterion must be independently verifiable by an outside reviewer:
    - [ ] <Specific, measurable outcome — not "everything works">

  ## Risks
  Markdown table. One row per risk, one mitigation per row:
  | Risk | Mitigation |
  |------|------------|
  | <risk> | <mitigation> |

  ## Tracking
  - Source of truth: `docs/flow-pack-methodology.md` + working state `.flow/state.md`
  - Milestone: <milestone name>
  - **One-pass confidence: X/10** (<one-sentence rationale for the score>)

### 5. Dry-run echo
  Print the EXACT commands to be executed (do not run them yet):
    cat > /tmp/umbrella-body.md << 'BODY_EOF'
    [full 7-field body as it will be submitted — show every line]
    BODY_EOF
    gh issue create \
      --title "<title>" \
      --body-file /tmp/umbrella-body.md \
      --label "umbrella" --label "flow" --label "<type>" \
      --milestone "<milestone-name>"

### 6. Approval gate
  Print:
    "──────────────────────────────────────────
     Awaiting approval. Type 'approve' to create the umbrella issue.
     Any other response = abort (no write).
    ──────────────────────────────────────────"
  Wait for user input. On "approve" (case-insensitive): proceed to step 7.
  On anything else: print "Aborted — no issue created." and stop.

### 7. Execute
  Run:
    cat > /tmp/umbrella-body.md << 'BODY_EOF'
    [7-field body]
    BODY_EOF
    gh issue create \
      --title "<title>" \
      --body-file /tmp/umbrella-body.md \
      --label "umbrella" --label "flow" --label "<type>" \
      --milestone "<milestone-name>"
  Capture the issue URL; extract the issue number N from the URL.

### 8. Confirm
  Run:
    gh issue view <N> --json number,title,labels,milestone \
      --jq '"#\(.number): \(.title) [\(.labels | map(.name) | join(","))] milestone=\(.milestone.title // "none")"'
  If labels or milestone are missing, print remediation:
    gh issue edit <N> --add-label <missing-label>
    gh issue edit <N> --milestone "<milestone-name>"

### 9. Gate and next-command
  Gate ✅ UMBRELLA CREATED when: created + all 7 sections present + labels ✅ + milestone ✅
  Gate ❌ FAILED when: gh issue create returned non-zero or confirm shows missing labels/milestone.
  Always print the next-command pointer, even on failure (so the user knows where to go):
    → Next: /flow-epics #<N>
```

**Output format block to include at the end of the command file:**
```text
## Output Format

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
  cat > /tmp/umbrella-body.md ...
  gh issue create --title "..." --body-file /tmp/umbrella-body.md --label ... --milestone ...
  [full body printed]

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

### Integration Points
```yaml
DOCS (tracked):
  - add: docs/flow-pack/commands/flow-umbrella.md
  - no modifications to docs/flow-pack-methodology.md required
    (it already describes /flow-umbrella in § Stage 2; no new content needed)

CLAUDE (local, gitignored):
  - add: .claude/commands/flow/flow-umbrella.md  (byte-copy via cp)

HAND-OFF:
  - /flow-umbrella ends with "→ Next: /flow-epics #N"
  - /flow-epics is E4 (#373); /flow-umbrella does NOT call it — it only prints the pointer
  - base_prp:prp-create is invoked per epic AFTER /flow-epics, not by /flow-umbrella
```

---

## Validation Loop

### Level 1: File presence + durable-source split
```bash
# tracked source of truth exists
test -f docs/flow-pack/commands/flow-umbrella.md && echo "OK tracked"

# local install exists and is gitignored (NOT durable)
test -f .claude/commands/flow/flow-umbrella.md && echo "OK local"
git check-ignore .claude/commands/flow/flow-umbrella.md   # must print the path

# local install == tracked template (no drift)
diff -q docs/flow-pack/commands/flow-umbrella.md \
        .claude/commands/flow/flow-umbrella.md && echo "OK no drift"

# only docs/flow-pack/commands/flow-umbrella.md is a new tracked file; .claude/** not staged
git status --short
```

Expected output:
- `OK tracked`, `OK local`, path printed by gitignore check, `OK no drift`
- `git status` shows one new `A` entry: `docs/flow-pack/commands/flow-umbrella.md`
- `.claude/commands/flow/flow-umbrella.md` does NOT appear in `git status`

### Level 2: Fresh-clone recovery reproduction
```bash
# simulate recovery: blow away the local install, regenerate, confirm identical
rm -f .claude/commands/flow/flow-umbrella.md
cp docs/flow-pack/commands/*.md .claude/commands/flow/
diff -q docs/flow-pack/commands/flow-umbrella.md \
        .claude/commands/flow/flow-umbrella.md && echo "OK recovery reproduces local"
```

### Level 3: Command structure smoke (manual inspection)
```bash
# Confirm all 9 process steps are present in the tracked template
grep -c "^### [0-9]\." docs/flow-pack/commands/flow-umbrella.md
# Expected: 9

# Confirm all 7 body section headings appear in the spec
grep "## Summary\|## Approach\|## Decomposition\|## Out of scope\|## Success criteria\|## Risks\|## Tracking" \
  docs/flow-pack/commands/flow-umbrella.md | wc -l
# Expected: 7

# Confirm dry-run and approval-gate keywords present
grep -c "dry.run\|DRY RUN\|approve\|approval" docs/flow-pack/commands/flow-umbrella.md
# Expected: >= 4 (dry-run in step 5, approval in step 6)

# Confirm the next-command pointer spec is present
grep "flow-epics" docs/flow-pack/commands/flow-umbrella.md
# Expected: at least one match showing "→ Next: /flow-epics #N"
```

### Level 4: Interactive smoke (post-install, manual)
```text
# In a Claude Code session, type: /flow-umbrella test-initiative
# Verify the command:
#   - Reads .flow/brainstorm-log.md (or notes its absence with a helpful error)
#   - Runs prerequisite checks (labels + milestone) and reports results
#   - Performs idempotency check
#   - Prints a dry-run echo with full 7-field body
#   - Blocks on approval gate (does NOT create without "approve")
#   - On "approve": creates the issue and prints #N + gate result
#   - Ends with "→ Next: /flow-epics #N"
# (No automated assertion — interactive command; verify output sections manually.)
```

---

## Tests / checks required
- [ ] Level 1 file-presence + gitignore + no-drift checks all pass (4 assertions green).
- [ ] Level 2 recovery reproduces the local install byte-for-byte.
- [ ] Level 3 structure smoke: 9 steps present, 7 section headings, ≥4 dry-run/approval hits,
      flow-epics pointer present.
- [ ] Provenance header present in both created files
      (`grep -l "provenance" docs/flow-pack/commands/flow-umbrella.md .claude/commands/flow/flow-umbrella.md`).
- [ ] `git status --short` shows `docs/flow-pack/commands/flow-umbrella.md` as the ONLY new tracked
      file; `.claude/commands/flow/flow-umbrella.md` does NOT appear.
- [ ] No standard repo gate is broken (markdown-only change → ruff/mypy/pyright/pytest unaffected;
      run `uv run ruff check . && uv run pytest -v -m "not integration"` to confirm green).
- [ ] `docs/flow-pack/commands/flow-prime.md` structure matches `flow-umbrella.md` structure
      (frontmatter → provenance → title → Objective → Process → Output Format → Arguments).
- [ ] E2/E4/E5 NOT implemented; no GitHub issues created.

---

## Final Validation Checklist
- [ ] Both files created + byte-identical (diff clean).
- [ ] Durable-source split holds: `docs/flow-pack/commands/flow-umbrella.md` tracked; `.claude/commands/flow/flow-umbrella.md` gitignored + regenerable.
- [ ] Command spec contains all 9 process steps in the correct order (prereq → idempotent → draft → dry-run → approval → execute → confirm → gate → next-pointer).
- [ ] 7-field body headings all present in the spec with correct names and field rules.
- [ ] Write discipline clauses all present: dry-run echo, approval gate, idempotency check, no write without "approve."
- [ ] --body-file approach used (not --body "...") for multi-line body safety.
- [ ] Type label derivation documented in the command spec.
- [ ] "→ Next: /flow-epics #N" pointer present in output format.
- [ ] E2 (#371) and E4 (#373) NOT touched; no epic creation in this scope.
- [ ] No commit/push performed; `uv.lock` + `docker-compose.lan.yml` left untouched.
- [ ] Branch for implementation: `feat/flow-pack-e3-flow-umbrella` off `dev`; commit (when user authorizes) references `(#372)`.

---

## Anti-Patterns to Avoid
- ❌ Treating `.claude/commands/flow/` as the source of truth (it's gitignored — durable truth is `docs/flow-pack/commands/flow-umbrella.md`).
- ❌ Hand-editing the local install instead of copying from the tracked template.
- ❌ Swapping the write-discipline order (prerequisite check must come before idempotency check, which must come before dry-run, which must come before execute).
- ❌ Using `--body "..."` instead of `--body-file` for multi-line gh issue create bodies.
- ❌ Putting fake `#N` refs for unborn epic issues in the Decomposition section.
- ❌ Creating epic issues inside /flow-umbrella — that is /flow-epics (E4 #373).
- ❌ Creating milestone or labels inside /flow-umbrella — those must exist from E1; the command validates and fails fast if missing.
- ❌ Diverging from the `docs/flow-pack/commands/flow-prime.md` file structure (frontmatter, section headings, output-format block, Arguments line).
- ❌ Staging `uv.lock` / `docker-compose.lan.yml` (pre-existing dirty worktree — leave alone).
- ❌ Implementing any part of E2 (/flow-brainstorm), E4 (/flow-epics), or E5 here.

---

## Confidence Score: 9/10

One-pass likelihood is high:
- Pattern is fully established by the E1 PRP + flow-prime.md (mirror exactly).
- All 9 process steps are specified to the line level, including exact `gh` commands.
- Methodology is fully reverse-engineered and dogfooded (`.flow/` state docs).
- Work is markdown-only: zero Python/TS runtime risk, no type system, no DB.
- Durable-source split is already understood by the E1 precedent.

−1 for two authoring judgment calls: (a) the quality of the synthesized 7-field body (depends on
what the V2 ship list says — must be coherent and match the live umbrella #368 style), and (b)
correctly handling the case where `.flow/brainstorm-log.md` is absent or partially formed (the
command must degrade gracefully with a clear error + `→ /flow-brainstorm` pointer).
