---
description: Capture baseline reality — delegate to core_piv_loop:prime, gather GitHub state, write .flow/state.md
---

<!-- provenance: flow-pack methodology stage 1 (continuation-discipline baseline step).
     Source of truth: docs/flow-pack/commands/flow-prime.md (tracked).
     Local install:   .claude/commands/flow/flow-prime.md (gitignored, regenerable from this file).
     Recovery: cp docs/flow-pack/commands/flow-prime.md .claude/commands/flow/flow-prime.md
     Full methodology: docs/flow-pack-methodology.md -->

# flow-prime: Baseline Reality Capture

## Objective

Capture the five baseline categories (repo state, docs, rules, issues, current state) needed to
plan a feature initiative. Produces two artifacts:

1. **Current-workflow-map** — inventory of installed commands, rules, CI workflows, hooks, and
   available skills.
2. **You-are-here snapshot** — branch, version, open issues, milestones, label gap, and a plain
   "what's missing for the flow: suite" summary.

Both artifacts are written to `.flow/state.md` (created if absent; phase sections updated if
present). The command ends by printing the gate result and the next-command pointer.

**DELEGATION: do NOT re-implement codebase priming.**
Run the `core_piv_loop:prime` skill for all codebase reading. This command adds only the GitHub
state gathering, workflow mapping, and `.flow/state.md` writing on top of it.

## Process

### 1. Codebase priming (delegate)

Run the `core_piv_loop:prime` skill. Let it produce the full project overview — purpose,
architecture, tech stack, core principles, and current state. Do not repeat that work here.

Supplement with:

!`git log -5 --oneline`

!`git status --short`

### 2. GitHub state

Gather the five GitHub categories:

!`gh issue list --state open --limit 20 --json number,title,labels --jq '.[] | "#\(.number): \(.title) [\(.labels | map(.name) | join(","))]"'`

!`gh milestone list --json number,title,state --jq '.[] | "#\(.number) \(.title) (\(.state))"'`

!`gh label list --json name --jq '[.[].name] | sort | join(", ")'`

!`gh pr list --state open --json number,title,headRefName --jq '.[] | "#\(.number): \(.title) → \(.headRefName)"'`

!`gh release list --limit 3 --json tagName,isPrerelease --jq '.[] | "\(.tagName)\(if .isPrerelease then " [pre]" else "" end)"'`

### 3. Workflow map

Inventory the installed flow: tooling without reading individual file contents.

!`ls .claude/commands/ 2>/dev/null && echo "---" && ls .claude/rules/ 2>/dev/null && echo "---" && ls .github/workflows/ 2>/dev/null`

!`ls .claude/commands/flow/ 2>/dev/null || echo "(no flow/ namespace yet)"`

!`ls .claude/hooks/ 2>/dev/null || echo "(no hooks dir)"`

Record:
- **Commands** — list of namespace dirs + top-level `.md` files under `.claude/commands/`. Note
  whether a `flow/` namespace exists.
- **Rules** — list of `.md` files under `.claude/rules/`. Note whether `umbrella-issue.md` exists.
- **Workflows** — list of `.github/workflows/*.yml` files.
- **Hooks** — files in `.claude/hooks/`.
- **Skills** — list the user-invocable skills visible in your context (from the system prompt or
  CLAUDE.md). Note reuse candidates for the flow: suite.

### 4. Synthesize and write .flow/state.md

Produce the two required sections:

**Current-workflow-map** (what exists today):
- Commands: `<namespace-dir>` → `[file1.md, file2.md, …]`; top-level `.md` files listed
- Rules: `[file1.md, …]`; highlight `umbrella-issue.md` if present
- Workflows: `[ci.yml, cd-release.yml, …]`
- Hooks: `[hook-file, …]`
- Skills (reuse candidates): `[skill-name: purpose, …]`
- flow/ namespace: ✅ installed / ❌ missing

**You-are-here snapshot** (current state):
- Branch: `<branch>` | Version: `<version from .release-please-manifest.json or CHANGELOG>`
- In-progress issues: `[#N title, …]`
- Active milestone: `<name>` or none
- Labels: umbrella=`[✅/❌]` epic=`[✅/❌]` flow=`[✅/❌]`
- Gap: concise plain-language statement of what the flow: suite still needs in this repo

Write these two sections to `.flow/state.md`:
- If the file **does not exist**, create it with a provenance HTML comment at the top and a
  `## Phase status` header, then append the two sections under `## Current workflow map` and
  `## You are here`.
- If the file **already exists**, find and update the two matching `##` sections in place; preserve
  all other content (Phase status, Gate decisions, Chosen workflow, Open epics, etc.).

### 5. Gate and next-command

Print the gate result using the output format below, then the next-command pointer.

Gate is ✅ **BASELINE CAPTURED** when all five categories are present:
- repo state (branch, recent commits, git status)
- docs (CLAUDE.md / AGENTS.md / README read)
- rules (`.claude/rules/` inventory)
- issues (open issues listed)
- current state (version, active milestone, label set)

Gate is ❌ **INCOMPLETE** if any category is missing or uncertain — list what's missing and why
before printing the next-command pointer (still print it so the user knows where to go next).

## Output Format

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  🗺️  flow-prime: Baseline Reality
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 Codebase (core_piv_loop:prime)
  [project overview summary from the delegated skill]

📋 GitHub State
  Open issues: N  |  Open PRs: M
  Milestones: <name or none>
  Labels: umbrella=[✅/❌]  epic=[✅/❌]  flow=[✅/❌]
  Recent release: <tag>

📋 Workflow Map
  Commands:  [namespaces / top-level files]
  Rules:     [files]  umbrella-issue.md=[✅/❌]
  Workflows: [files]
  flow/ namespace: [✅/❌]

📋 You Are Here
  Branch: <branch>  |  Version: <version>
  In-progress: [#N title, …]
  Gap: <plain-language description of what's missing>

────────────────────────────────────────────
  [✅/❌] BASELINE CAPTURED → .flow/state.md updated
────────────────────────────────────────────

→ Next: /flow-brainstorm <initiative description>
```

## Arguments

`$ARGUMENTS` — optional free-text initiative description passed through to the gate result and
the next-command pointer (e.g., `/flow-prime integrate flow-pack methodology`). If omitted, the
you-are-here snapshot stands on its own.
