name: "flow-pack E2 — /flow-brainstorm command"
description: |
  Implement the /flow-brainstorm command: the V1-naive-plan → 3-read-only-agent-research →
  5-dimensional-score → V2-ship/defer pipeline for the flow-pack methodology suite.
  Delivers two files (tracked template + local install); no backend, frontend,
  migration, or runtime changes.

**Issue:** #371 | **Umbrella:** #368 | **Branch:** `feat/flow-brainstorm-command`
**Depends on:** E1 #369 merged (flow-prime live, `docs/flow-pack/commands/` exists, labels/milestone created).
**Working-tree caveat:** `docker-compose.lan.yml` (untracked) + `uv.lock` (M) are pre-existing — do NOT stage either.

---

## Goal

Implement `/flow-brainstorm` as E2 of the flow-pack suite. Deliverables are two files:

| File | Action | Role |
|------|--------|------|
| `docs/flow-pack/commands/flow-brainstorm.md` | CREATE | Tracked canonical template — committed, source of truth |
| `.claude/commands/flow/flow-brainstorm.md` | CREATE | Local runtime install — gitignored, byte-copy of tracked template |

No `app/`, `frontend/`, `alembic/`, or any runtime code is touched. No GitHub writes.
No E3 (`/flow-umbrella`) or E4 (`/flow-epics`) behavior is implemented.

### Success Criteria

- [ ] `docs/flow-pack/commands/flow-brainstorm.md` exists, committed under `docs(repo): add /flow-brainstorm command — E2 of flow-pack suite (#371)`
- [ ] `.claude/commands/flow/flow-brainstorm.md` is a byte-copy (`diff` exits 0)
- [ ] Command file follows the exact structure of `docs/flow-pack/commands/flow-prime.md` (frontmatter, provenance comment, numbered steps, output format block, $ARGUMENTS section)
- [ ] All 5 scoring dimensions defined: Value, Risk, Readiness, Complexity, Evidence (1–10 each, max 50)
- [ ] Score bands enforced: ≥ 40 → SHIP, 36–39 → NEGOTIATE (human gate), < 36 → DEFER with written reason
- [ ] Exactly 3 read-only subagents: A (Known Issues), B (Best Practices), C (Dependencies)
- [ ] `.flow/brainstorm-log.md` append rules documented (append-only, round-numbered)
- [ ] Human approval gate printed before next-command pointer
- [ ] Next-command pointer: `→ Next: /flow-umbrella <initiative>`
- [ ] Only `docs/flow-pack/commands/flow-brainstorm.md` committed; `.claude/` never staged

---

## Why

The flow-pack pipeline (`docs/flow-pack-methodology.md`) is a 4-command chain:

```
/flow-prime → /flow-brainstorm → /flow-umbrella → /flow-epics
```

E1 (flow-prime, PR #370) is merged. E2 delivers the second link: it turns a baseline snapshot
into a scored, human-approved V2 ship/defer list ready for `/flow-umbrella`. Without it, the
pipeline breaks at the first handoff — a user can prime but cannot plan.

The command is pure tooling: no application code, no database changes, no new runtime
dependencies. It encodes the "V1 → critique → 3-agent research → 5-dim score → V2" pattern
defined in `docs/flow-pack-methodology.md § /flow-brainstorm`.

---

## What

### Behavior summary (what the command does when invoked)

1. Reads initiative description from `$ARGUMENTS` or falls back to `.flow/state.md` "Gap"
2. Produces **V1** — flat bullet list of 5–10 items, from baseline alone, unscored, labeled "V1"
3. Applies **critique gate** — tags each V1 item with `{assumption, scope-creep, no-evidence}`; does NOT modify V1
4. Spawns **exactly 3 read-only research subagents** (Agent tool) in parallel:
   - Agent A — Known Issues: open bugs and prior incidents relevant to V1
   - Agent B — Best Practices: docs, existing skills, reuse candidates
   - Agent C — Dependencies: blockers, upstream availability, API confirmation
5. **Scores** every V1 item on 5 dimensions (1–10 each, max 50)
6. Applies **score-band rule**: ≥ 40 SHIP · 36–39 NEGOTIATE (stop for human) · < 36 DEFER
7. Waits for human approval on negotiate-zone items before constructing V2
8. Produces **V2**: ship list + defer list with explicit one-clause reasons + X/10 confidence
9. **Appends** decision trail (V1, scores, defer reasons) to `.flow/brainstorm-log.md`
10. Waits for **human approval gate** on the V2 list
11. Prints gate result + `→ Next: /flow-umbrella <initiative>`

### What the command does NOT do

- Does not create GitHub issues (E3 /flow-umbrella)
- Does not generate 7-field umbrella bodies (E3)
- Does not link sub-issues (E4 /flow-epics)
- Does not write to `.flow/state.md` (that is owned by /flow-prime)
- Does not make any GitHub writes before explicit human approval

---

## All Needed Context

### Documentation & References

```yaml
- file: docs/flow-pack-methodology.md
  section: "§ /flow-brainstorm — V1 → score → V2" and "§ Invariants"
  why: The AUTHORITATIVE spec. Contains the 5 dimensions, score bands, 3-agent mandates,
       and invariants. Read this section before writing the command — the PRP quotes the
       key facts but the methodology doc is the single source of truth.

- file: docs/flow-pack/commands/flow-prime.md
  why: The CANONICAL PATTERN for flow: command files. Mirror its structure exactly:
       YAML frontmatter (description:), HTML provenance comment block, ## heading,
       ## Objective paragraph, ## Process numbered steps, !-prefix bash commands,
       ## Output Format fenced block, ## Arguments section. Do not invent structure.

- file: .flow/brainstorm-log.md
  why: The EXISTING append log (created during E1 dogfood). Shows the exact format to
       replicate: provenance comment on creation, ## Round N — YYYY-MM-DD heading,
       V1 bullets, critique flags, 5-dim score notation "Value/Risk/Readiness/Complexity/Evidence",
       SHIP/NEGOTIATE/DEFER notation, user-response line. The command must append in exactly
       this format.

- file: .flow/state.md
  why: Input to the command at runtime. "You are here" and "Gap" sections provide initiative
       context when $ARGUMENTS is absent. Also holds the phase status the command should
       update to "[x] Phase N — /flow-brainstorm done" (see Update rules below).

- file: .claude/rules/umbrella-issue.md
  why: Downstream contract — shows what /flow-umbrella expects as input from /flow-brainstorm.
       Confirms the V2 ship list is the ONLY durable output; V1 + scores are transient
       working-state artifacts (invariant: "V1 is transient").
```

### Desired codebase tree

```
docs/flow-pack/commands/
  flow-prime.md          ← existing (pattern reference, DO NOT modify)
  flow-brainstorm.md     ← CREATE (tracked canonical template)

.claude/commands/flow/
  flow-prime.md          ← existing
  flow-brainstorm.md     ← CREATE (byte-copy of tracked template)

.flow/                   ← existing (runtime working dir, NOT committed)
  state.md               ← existing (input at runtime)
  brainstorm-log.md      ← existing (append target at runtime)
```

### Known Gotchas

```
# GOTCHA 1: .claude/ is gitignored — NEVER commit the local install
# docs/flow-pack/commands/flow-brainstorm.md = durable source of truth (commit this)
# .claude/commands/flow/flow-brainstorm.md   = regenerable local install (do NOT commit)
# Source: docs/flow-pack-methodology.md § "Durable-source split"
# Recovery line: cp docs/flow-pack/commands/flow-brainstorm.md .claude/commands/flow/flow-brainstorm.md
# This MUST appear in the provenance comment of the command file.

# GOTCHA 2: Subagents are PROSE instructions, NOT ! bash commands
# The 3 research subagents are invoked via the Agent tool, described as prose in the
# command file: "Spawn 3 read-only research subagents in parallel (Agent tool): ..."
# They are NOT `!`-prefixed lines. A `!` prefix runs bash; Agent tool invocations
# are instructional prose that Claude follows when executing the command.
# Example from flow-prime.md: !`git log -5 --oneline` is bash.
# "Spawn Agent A (Known Issues) with the following prompt: ..." is agent invocation prose.

# GOTCHA 3: brainstorm-log.md is APPEND-ONLY (NOT HTML markers like state.md)
# state.md uses <!-- FLOW-PRIME:...:START/END --> marker pairs (replacement strategy).
# brainstorm-log.md is different — each run appends a NEW ## Round N section.
# NEVER overwrite or replace previous rounds.
# Update rule in the command file must say:
#   - File absent → create with provenance header + ## Round 1 section
#   - File exists → count current max N, append ## Round (N+1) — <date>

# GOTCHA 4: Score-band NEGOTIATE (36–39) requires a HARD STOP
# Items in 36–39 MUST be surfaced to the human before constructing V2.
# The command must STOP and present the negotiate items with their scores and
# one-sentence rationale, asking the human to decide: ship or defer.
# Only after the human responds does V2 get constructed.
# Do NOT auto-ship negotiate items. Per methodology § Invariants: "Score bands are hard."

# GOTCHA 5: Every DEFER item MUST have an explicit one-clause written reason
# Per methodology § Invariants: "Every defer has a reason. A defer item with no
# written reason is a process failure."
# Format: "<item title> (score: X/50): DEFER — <one clause reason>"
# Acceptable reason: "DEFER — overlaps existing analyzing-ai-repos skill; revisit if a
#   future initiative needs deep reverse-engineering."
# NOT acceptable: "DEFER" alone, or "DEFER — not needed now"

# GOTCHA 6: V1 must be explicitly labeled "V1" and UNSCORED
# Per methodology: "labeled 'V1' explicitly" and the item list is "unscored".
# Do not add dimension scores in V1. V1 is the raw brainstorm before research.
# The critique gate TAGS items (flags) but does not score them.

# GOTCHA 7: Critique flags are LABELS, NOT FIXES
# The critique gate attaches zero or more flags to each V1 item:
#   assumption — relies on an unverified fact
#   scope-creep — touches E3/E4/E5 or out-of-scope systems
#   no-evidence — no concrete codebase grounding for the need
# The flags focus research agents but do NOT change V1 text.

# GOTCHA 8: $ARGUMENTS fallback chain
# 1. If $ARGUMENTS is non-empty, use it as the initiative description.
# 2. Else, read .flow/state.md "Gap" line.
# 3. Else, ask the user: "What initiative should I brainstorm? (1–3 sentences)"

# GOTCHA 9: The command file IS the agent instruction — no code runs
# Unlike a Python module or TypeScript file, the command file is read by Claude Code
# and followed as instructions. "Implementation" = writing the markdown correctly.
# The PRP's task is to specify the exact content of that markdown file.
```

---

## Implementation Blueprint

There are two tasks: (1) write the tracked template file, (2) create the local install copy. Task 3 is the commit.

---

### Task 1: Write `docs/flow-pack/commands/flow-brainstorm.md`

Write this exact file. Every section is specified below. Mirror the structure of
`docs/flow-pack/commands/flow-prime.md` — do not invent new structural conventions.

---

**File content spec** (write verbatim, substituting `<YYYY-MM-DD>` with today):

```markdown
---
description: V1 naive plan → 3-read-only-agent research → 5-dim score → V2 ship/defer list
---

<!-- provenance: flow-pack methodology stage 2 (V1 → V2 planning pipeline).
     Source of truth: docs/flow-pack/commands/flow-brainstorm.md (tracked).
     Local install:   .claude/commands/flow/flow-brainstorm.md (gitignored, regenerable from this file).
     Recovery: cp docs/flow-pack/commands/flow-brainstorm.md .claude/commands/flow/flow-brainstorm.md
     Full methodology: docs/flow-pack-methodology.md -->

# flow-brainstorm: V1 → Score → V2

## Objective

Turn a baseline initiative description into a scored, human-approved V2 ship/defer list ready
for `/flow-umbrella`. Produces three outputs:

1. **V1** — flat bullet list of 5–10 candidate items, from baseline alone, unscored, labeled "V1".
2. **V2** — approved ship list + explicit defer list + X/10 one-pass confidence score.
3. **Log entry** — full decision trail appended to `.flow/brainstorm-log.md`.

The three read-only research subagents are the engine of this command. Claude spawns exactly 3
(Agent A — Known Issues, Agent B — Best Practices, Agent C — Dependencies) via the Agent tool,
waits for all three, then synthesizes their findings into the score table.

This command makes NO GitHub writes. It ends by printing the approved V2 list and the next-command
pointer. All GitHub writes (issue creation, labeling, linking) belong to E3 `/flow-umbrella`.

**DELEGATION:** Do not re-implement codebase priming. If the baseline context needs refreshing,
run `/flow-prime` first.

## Process

### 1. Read baseline context

!`ls .flow/ 2>/dev/null || echo "(no .flow/ directory yet)"`

Determine the initiative description:
- If `$ARGUMENTS` is non-empty → use it.
- Else → read `.flow/state.md` and extract the "Gap" line from the "You are here" section.
- Else → ask the user: "What initiative should I brainstorm? Provide 1–3 sentences."

Read `.flow/brainstorm-log.md` (if it exists) to determine the current round count. The new
round will be Round N+1 (or Round 1 if the file does not exist yet).

!`test -f .flow/brainstorm-log.md && grep -c "^## Round" .flow/brainstorm-log.md || echo "0"`

### 2. Produce V1 — naive plan (UNSCORED)

Generate a flat bullet list of 5–10 candidate items **from baseline knowledge only** — no research
yet. Every item must be:

- **Unscored** — no dimension scores; plain text only.
- **Labeled "V1"** — the section heading must read `## V1 — Naive Plan (N items, unscored)`.
- **Descriptive** — format: `- <item title>: <one-sentence description of what and why>`.

Coverage heuristics: include obvious high-value items, known technical debt, upstreams that may
be blocked, and at least one item that is likely out of scope (to stress-test the critique gate).

### 3. Critique gate — tag V1 items (do NOT fix them)

For each V1 item, attach zero or more flags. Flags are labels only — do not change V1 text.

| Flag | When to apply |
|------|---------------|
| `assumption` | Relies on a fact not verified against the codebase or docs |
| `scope-creep` | Touches E3/E4/E5 behavior or an out-of-scope system |
| `no-evidence` | No concrete codebase grounding for the stated need |

Present as: `- <item title> [assumption, scope-creep]` or `- <item title> [none]`.

The flags guide the research agents. An `assumption`-flagged item means "Agent A should verify
this claim." A `scope-creep` flag means "Agent B should confirm boundaries."

### 4. Spawn 3 read-only research subagents in parallel

Invoke the **Agent tool** to spawn all three concurrently. Each subagent is read-only — it MUST
NOT write files or make GitHub writes. Pass the V1 items + critique flags in the prompt.

**Agent A — Known Issues**

Prompt:
```
You are a read-only research agent. You MUST NOT write files or make GitHub writes.

Initiative: <initiative-description>
V1 items (with critique flags): <paste V1 list with flags>

Task: Read the open GitHub issues, recent git log, and .flow/state.md.
Report:
  1. Which V1 items are blocked by or related to open issues? (cite #N)
  2. Which V1 items are partially done (recent branches/PRs touching them)?
  3. Which V1 `assumption` flags are contradicted by known incidents or bugs?

Output: concise bullet list, #N refs where applicable. Read-only.
```

**Agent B — Best Practices**

Prompt:
```
You are a read-only research agent. You MUST NOT write files or make GitHub writes.

Initiative: <initiative-description>
V1 items (with critique flags): <paste V1 list with flags>

Task: Read CLAUDE.md, AGENTS.md, docs/flow-pack-methodology.md, and .claude/rules/.
Report:
  1. Which V1 items align with or contradict current best practices?
  2. Which V1 items are already covered by an existing skill or command? (reuse opportunity)
  3. Which V1 `scope-creep` flags are confirmed — item truly belongs to E3/E4/E5?

Output: concise bullet list. Read-only.
```

**Agent C — Dependencies**

Prompt:
```
You are a read-only research agent. You MUST NOT write files or make GitHub writes.

Initiative: <initiative-description>
V1 items (with critique flags): <paste V1 list with flags>

Task: Read pyproject.toml, frontend/package.json, docker-compose.yml,
and docs/_base/API_CONTRACTS.md.
Report:
  1. Which V1 items have unresolved upstream dependencies or API blockers?
  2. Which V1 `no-evidence` flags are confirmed — no codebase grounding found?
  3. Any dependency pinning or version conflicts that affect V1 items?

Output: concise bullet list. Read-only.
```

Wait for all three agents before proceeding.

### 5. Score V1 items on 5 dimensions

Use agent findings as evidence for the Evidence dimension. Score each item 1–10 per dimension:

| Dimension | 1 = low | 10 = high | Evidence dimension note |
|-----------|---------|-----------|------------------------|
| **Value** | Cosmetic / irrelevant | Core user outcome | — |
| **Risk** | Low risk, well-understood | High risk, many unknowns | Higher Risk = lower desirability |
| **Readiness** | Many blockers open | All upstreams clear | Blocked = lower score |
| **Complexity** | Trivial | Enormous effort | Higher Complexity = lower desirability |
| **Evidence** | Pure assumption | Fully verified by agents | Directly from agent reports |

Note: Risk and Complexity score INVERSELY — a low-risk, low-complexity item scores 9–10, not 1–2.
(A high-risk item is less desirable, so it scores lower on the Risk dimension.)

Present the score table:

```
| Item | Value | Risk | Readiness | Complexity | Evidence | Total | Band |
|------|-------|------|-----------|------------|----------|-------|------|
| ...  |   8   |   7  |     9     |     6      |    9     |  39   | 🟡 NEGOTIATE |
```

Band indicators:
- `✅ SHIP` — total ≥ 40
- `🟡 NEGOTIATE` — total 36–39 (requires human decision before V2)
- `❌ DEFER` — total < 36 (requires explicit one-clause written reason)

### 6. Handle negotiation zone (36–39 items)

If any items score 36–39, **STOP and surface to human** before constructing V2:

```
N item(s) are in the negotiation zone (score 36–39):

  - <item>: score 38. Rationale: <one sentence from agent reports>.
    Research note: Agent B flagged this as covered by an existing skill (reuse potential).

Decision needed for each item — respond 'ship', 'defer', or 'defer: <reason>':
```

Wait for human response for each negotiate item. Record the decision in the round log.

If all items are SHIP or DEFER, skip this step.

### 7. Produce V2 — ship list and defer list

**V2 ship list** (items scoring ≥ 40, plus negotiate items the human shipped):

```
## V2 — Ship List

1. <item title> (score: X/50): <one-sentence rationale drawing on agent evidence>
2. ...
```

**Defer list** (items scoring < 36, plus negotiate items the human deferred):

```
## Defer List

- <item title> (score: X/50): DEFER — <explicit one-clause reason>
```

Every defer item MUST have an explicit reason. "DEFER — not needed now" is not acceptable.
Good example: "DEFER — overlaps the existing `analyzing-ai-repos` skill; fold into /flow-prime
if deep external analysis is needed."

**One-pass confidence score** on the V2 ship list:

```
One-pass confidence: X/10 — <one sentence: what gives confidence and what remains uncertain>
```

### 8. Append to `.flow/brainstorm-log.md`

Update rules:
- **File absent** → create with provenance header + `# /flow-brainstorm — decision log` + first round section.
- **File exists** → count existing `## Round` headings, append `## Round (N+1) — <date>`.
- **NEVER overwrite previous rounds.** The log is append-only.

Provenance header (write only on creation):
```
<!-- provenance: /flow-brainstorm decision trail. Append-only. NOT committed. -->
# /flow-brainstorm — decision log
```

Round section format (exact fields — one paragraph per field, bold label):

```markdown
## Round N — YYYY-MM-DD

**Initiative:** <initiative description>
**V1 (N items, unscored):** (1) <item1> (2) <item2> ...
**Critique flags:** <"item title [flags]" for flagged items, or "none">
**Research:** spawned 3 read-only subagents (A Known Issues, B Best Practices, C Dependencies)
**Agent findings (evidence-backed):**
- A: <key findings, one line>
- B: <key findings, one line>
- C: <key findings, one line>
**5-dim scores (Value/Risk/Readiness/Complexity/Evidence, ≥40 ship):**
- <item title> V/R/Re/C/E=total ✅ SHIP / 🟡 NEGOTIATE → <decision> / ❌ DEFER
**V2 SHIP:** <item1>, <item2>, ...  **DEFER:** <item> — <reason>; ...
**One-pass confidence:** X/10 — <rationale>
**User response:** <what the human decided at the approval gate>
```

### 9. Human approval gate

Print V2 ship list and defer list in full. Print the one-pass confidence score.

```
────────────────────────────────────────────
  Approve V2 ship list?
    'approve' → write log entry + print next-command pointer
    'revise: <instruction>' → adjust scores or categorizations
────────────────────────────────────────────
```

After human approves, write the log entry (Step 8) with `User response: approved`.

### 10. Gate result and next-command

Print using the Output Format below.

## Output Format

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  💡 flow-brainstorm: V1 → Score → V2
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 Baseline Context
  Initiative: <description>
  Source: [.flow/state.md gap | $ARGUMENTS]
  Brainstorm round: N (log entry Round N appended)

📋 V1 — Naive Plan (N items, unscored)
  1. <item title>: <one-sentence description>  [flags or none]
  2. ...

📋 Research (3 agents — parallel)
  Agent A (Known Issues): <2-line summary>
  Agent B (Best Practices): <2-line summary>
  Agent C (Dependencies): <2-line summary>

📋 Scoring
  | Item | V | R | Re | C | E | Total | Band |
  |------|----|----|----|----|----|-------|------|
  ...

📋 V2 — Approved List
  Ship (N items): <item1>, <item2>, ...
  Defer (M items): <item> — <reason>; ...
  One-pass confidence: X/10

────────────────────────────────────────────
  ✅ V2 APPROVED → .flow/brainstorm-log.md updated (Round N)
────────────────────────────────────────────

→ Next: /flow-umbrella <initiative>
```

## Arguments

`$ARGUMENTS` — the initiative description, passed as free text
(e.g., `/flow-brainstorm add batch forecasting to the system`).
If omitted, the command falls back to `.flow/state.md` Gap line; if state.md is absent,
asks the user directly. Passed through to the gate result and the next-command pointer.
```

---

### Task 2: Create `.claude/commands/flow/flow-brainstorm.md` (local runtime install)

After writing Task 1, create the local install as a byte-copy:

```bash
cp docs/flow-pack/commands/flow-brainstorm.md .claude/commands/flow/flow-brainstorm.md
```

Verify no drift:

```bash
diff docs/flow-pack/commands/flow-brainstorm.md .claude/commands/flow/flow-brainstorm.md \
  && echo "OK — identical" || echo "DRIFT DETECTED — fix before proceeding"
```

The local install MUST NOT be committed (`.claude/` is gitignored). Its only purpose is to
make `/flow:flow-brainstorm` available in Claude Code for the current working session.

---

### Task 3: Commit the tracked template only

Stage ONLY the tracked template:

```bash
# Verify issue #371 is open before committing
gh issue view 371 --json state --jq '.state'   # must return "OPEN"

# Stage ONLY the tracked template
git add docs/flow-pack/commands/flow-brainstorm.md

# Verify staged files — must show only the tracked template
git diff --cached --name-only

# Commit
git commit -m "docs(repo): add /flow-brainstorm command — E2 of flow-pack suite (#371)"
```

**Do NOT stage:**
- `.claude/commands/flow/flow-brainstorm.md` (gitignored — correct that `git add` ignores it)
- `uv.lock` (pre-existing modification unrelated to this PRP)
- `docker-compose.lan.yml` (local-only untracked file)

---

## Validation Loop

### Level 1: File existence and byte-identity

```bash
# Both files must exist
test -f docs/flow-pack/commands/flow-brainstorm.md && echo "tracked: OK" || echo "tracked: MISSING"
test -f .claude/commands/flow/flow-brainstorm.md   && echo "local:   OK" || echo "local:   MISSING"

# No drift
diff docs/flow-pack/commands/flow-brainstorm.md .claude/commands/flow/flow-brainstorm.md \
  && echo "identical: OK" || echo "DRIFT: fix with cp"
```

### Level 2: Content completeness

```bash
F=docs/flow-pack/commands/flow-brainstorm.md

# Frontmatter
head -3 "$F" | grep -q "description:" && echo "frontmatter: OK" || echo "frontmatter: MISSING"

# Provenance comment — must match flow-prime pattern
grep -q "Source of truth: docs/flow-pack/commands/flow-brainstorm.md" "$F" && echo "provenance: OK"

# All 5 scoring dimensions
for dim in Value Risk Readiness Complexity Evidence; do
  grep -q "\*\*${dim}\*\*\|${dim} |${dim}:" "$F" && echo "dim-${dim}: OK" || echo "dim-${dim}: MISSING"
done

# Score bands
grep -q "≥ 40\|>= 40\|≥40" "$F" && echo "band-40: OK" || echo "band-40: MISSING"
grep -q "36–39\|36-39"      "$F" && echo "band-36-39: OK" || echo "band-36-39: MISSING"
grep -q "< 36\|<36"         "$F" && echo "band-36: OK" || echo "band-36: MISSING"

# Exactly 3 named agents
grep -c "Agent [ABC]" "$F" | xargs -I{} sh -c '[ {} -ge 3 ] && echo "3-agents: OK" || echo "3-agents: MISSING"'

# Append-only rule for brainstorm-log
grep -q "append\|Append-only" "$F" && echo "append-rule: OK" || echo "append-rule: MISSING"

# Next-command pointer
grep -q "flow-umbrella" "$F" && echo "next-cmd: OK" || echo "next-cmd: MISSING"

# $ARGUMENTS section
grep -q "ARGUMENTS\|\$ARGUMENTS" "$F" && echo "args: OK" || echo "args: MISSING"
```

### Level 3: Commit integrity

```bash
# Commit message format
git log -1 --format='%s' | grep -E "^docs\(repo\): add /flow-brainstorm command" \
  && echo "commit-msg: OK" || echo "commit-msg: WRONG"

# Issue reference
git log -1 --format='%s' | grep -q "#371" && echo "issue-ref: OK" || echo "issue-ref: MISSING"

# .claude/ not committed
git show --name-only HEAD | grep ".claude/" \
  && echo "ERROR: .claude/ committed — must not be" || echo ".claude/-clean: OK"

# uv.lock not committed
git show --name-only HEAD | grep "uv.lock" \
  && echo "ERROR: uv.lock committed — unstage it" || echo "uv.lock-clean: OK"

# Only the tracked template committed
git show --name-only HEAD | grep -v "^commit\|^Author\|^Date\|^$\|^    " \
  | grep -v "^docs/flow-pack/commands/flow-brainstorm.md$" \
  && echo "UNEXPECTED FILES in commit" || echo "commit-scope: OK"
```

### Level 4: Functional smoke test (manual, after commit)

In Claude Code, run:
```
/flow:flow-brainstorm test initiative
```

Verify sequentially:
1. ✅ V1 produced: 5–10 items, labeled "V1 — Naive Plan", no dimension scores visible
2. ✅ Critique flags applied: each item annotated with `[assumption|scope-creep|no-evidence|none]`
3. ✅ 3 subagents spawned: Agent A, Agent B, Agent C appear in Agent tool output
4. ✅ Score table produced: all 5 columns (V, R, Re, C, E) + Total + Band
5. ✅ Score bands applied: items labeled SHIP / NEGOTIATE / DEFER
6. ✅ Negotiate gate fires (if any 36–39 items): human asked before V2 constructed
7. ✅ Defer items carry explicit one-clause reasons
8. ✅ `.flow/brainstorm-log.md` appended with new `## Round N` section
9. ✅ Approval gate prints before next-command pointer
10. ✅ Gate result ends with `→ Next: /flow-umbrella <initiative>`

---

## Final Validation Checklist

- [ ] `docs/flow-pack/commands/flow-brainstorm.md` exists, committed, correct branch
- [ ] `.claude/commands/flow/flow-brainstorm.md` is a byte-copy (`diff` exits 0)
- [ ] Frontmatter `description:` present in tracked template
- [ ] Provenance comment matches flow-prime.md pattern (source-of-truth, recovery cp line)
- [ ] All 5 scoring dimensions named: Value, Risk, Readiness, Complexity, Evidence
- [ ] Score bands documented: ≥ 40 SHIP · 36–39 NEGOTIATE · < 36 DEFER
- [ ] Negotiate zone requires human stop — not auto-shipped
- [ ] Every DEFER item carries explicit one-clause reason (invariant from methodology)
- [ ] Exactly 3 subagents: A (Known Issues), B (Best Practices), C (Dependencies)
- [ ] Subagent prompts are read-only — "MUST NOT write files or make GitHub writes"
- [ ] `.flow/brainstorm-log.md` append rules documented (append-only, round-numbered)
- [ ] Brainstorm log: provenance header only on creation; round section on every run
- [ ] Human approval gate documented before the next-command pointer
- [ ] Next-command pointer: `→ Next: /flow-umbrella <initiative>`
- [ ] `$ARGUMENTS` fallback chain documented (args → state.md gap → ask user)
- [ ] Only `docs/flow-pack/commands/flow-brainstorm.md` committed; `.claude/` never staged
- [ ] `uv.lock` and `docker-compose.lan.yml` NOT staged
- [ ] Commit message: `docs(repo): add /flow-brainstorm command — E2 of flow-pack suite (#371)`
- [ ] `gh issue view 371 --json state --jq '.state'` returns `"OPEN"` before commit
- [ ] Level 1–3 validation scripts all pass

---

## Anti-Patterns to Avoid

- ❌ Don't commit `.claude/commands/flow/flow-brainstorm.md` — it is gitignored and local-only
- ❌ Don't implement GitHub writes (issue create / label / sub-issue link) — E3/E4 scope
- ❌ Don't auto-ship negotiate-zone items (36–39) — always stop and ask the human
- ❌ Don't write a defer item without a one-clause explicit reason — process failure per invariants
- ❌ Don't spawn 2 agents or 4 agents — exactly 3, always
- ❌ Don't use HTML START/END markers in brainstorm-log.md — that pattern belongs to state.md
- ❌ Don't score V1 items before running the research agents — scoring depends on Evidence
- ❌ Don't stage `uv.lock` or `docker-compose.lan.yml`
- ❌ Don't invent new structural conventions for the command file — mirror flow-prime.md exactly
- ❌ Don't use `!` prefix for Agent tool invocations — `!` is for bash, not for subagent spawning
