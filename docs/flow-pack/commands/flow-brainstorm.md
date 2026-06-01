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
