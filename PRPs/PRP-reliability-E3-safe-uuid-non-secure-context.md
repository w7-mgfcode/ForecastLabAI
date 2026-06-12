name: "PRP — Reliability E3: safe-UUID fallback for non-secure contexts (Showcase LAN-HTTP white-screen)"
description: |
  Parallel epic of umbrella #380 (platform reliability hardening), after Foundation E1 (#334).
  Issue: #332 · Branch: `fix/ui-safe-uuid-non-secure-context` off `dev` · Commit scope: `ui`
  (frontend-only — the single mutation surface is `frontend/src/`; zero backend changes).

---

## Goal

On any plain-HTTP LAN origin (e.g. `http://10.0.0.226:5173/showcase`), the Showcase page must
survive pipeline completion instead of white-screening. Today `RunHistoryStrip.tsx:75` calls
`crypto.randomUUID()` directly; outside a secure context (`window.isSecureContext === false`)
that property is `undefined`, the `TypeError: crypto.randomUUID is not a function` throws
**during render** (the append happens in the render-phase `setItems` updater), and React
unmounts the whole tree → blank page while the backend pipeline keeps completing fine.

**Deliverable:**
1. A new shared utility `frontend/src/lib/uuid-utils.ts` exporting `safeRandomUUID(): string` —
   delegates to `crypto.randomUUID()` when available, falls back to an RFC-4122-v4 generator
   built on `crypto.getRandomValues()` (which is NOT secure-context-gated), with a final
   `Math.random()`-based last resort if Web Crypto is absent entirely.
2. A colocated vitest suite `frontend/src/lib/uuid-utils.test.ts`.
3. `RunHistoryStrip.tsx:75` switched to `safeRandomUUID()` + a non-secure-context regression
   case added to `RunHistoryStrip.test.tsx`.
4. An ESLint `no-restricted-properties` guard in `frontend/eslint.config.js` that bans direct
   `crypto.randomUUID` member access repo-wide (exempting the helper itself), so the bug class
   cannot silently come back at a future call site.

**Success definition:** a full showcase run over a LAN-IP HTTP origin completes and the
"Recent runs" strip renders the new entry (manual dogfood, umbrella #380 risk row: "LAN-HTTP
behavior not covered by CI"); vitest covers both helper paths and the component regression;
`pnpm tsc --noEmit && pnpm lint && pnpm test --run` all green.

## Why

- **Demo-killer with a silent failure mode.** Anyone demoing the showcase from another device
  (the whole point of the LAN setup) sees the page freeze/blank at the finish line and reads it
  as "the pipeline hung at step 21" — the backend actually succeeded (runs registered, ops
  snapshot computed, scenario plans persisted). Diagnosed in issue #332 via Playwright:
  `localhost` → `isSecureContext=true` (works); LAN IP → `isSecureContext=false` (crashes).
- **Umbrella #380 acceptance** explicitly lists: "`/showcase` completes a full run over
  plain-HTTP LAN origin without white-screen; UUID fallback util has a vitest (#332 closed)".
- **One-line bug, repo-wide guard.** The audit found exactly ONE call site today, but nothing
  stops the next feature from re-introducing `crypto.randomUUID()`. The lint guard mirrors the
  repo's "the test is the spec" guard-rail ethos (cf. `test_leakage.py`,
  `test_strict_mode_policy.py`) at the cheapest possible layer.

## What

### Behavior change

| Surface | Today | After |
|---------|-------|-------|
| `/showcase` on `http://<lan-ip>:5173` at `pipeline_complete` | `TypeError: crypto.randomUUID is not a function` thrown in render → React tree unmounts → white screen | `safeRandomUUID()` falls back to the `getRandomValues` v4 generator → history entry appended, "Recent runs" strip renders |
| `/showcase` on `http://localhost:5173` or HTTPS | works (`crypto.randomUUID` defined) | **unchanged** — helper delegates to the native call |
| Any future `crypto.randomUUID(` member access in `frontend/src` | compiles + lints clean, crashes at runtime on LAN HTTP | `eslint .` fails with a message pointing at `safeRandomUUID()` |

### Out of scope

- No backend change, no API change, no `docs/_base/` contract update (frontend-only fix).
- No new npm dependency (`uuid` / `nanoid` considered and rejected — a ~20-line util keeps the
  dependency-light footprint per `.claude/rules/product-vision.md`; both packages would be
  pulled in for exactly one call site).
- Other secure-context-gated APIs: audit confirmed zero uses of `crypto.subtle` and
  `navigator.clipboard` in `frontend/src` — nothing else to fix.

### Success Criteria

- [ ] `safeRandomUUID()` returns the native `crypto.randomUUID()` value when available
- [ ] With `crypto.randomUUID` absent but `getRandomValues` present (the real LAN-HTTP shape),
      output matches `/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/`
      and successive calls differ
- [ ] With `crypto` absent entirely, the `Math.random` last resort still matches the v4 shape
- [ ] `RunHistoryStrip` renders a history entry without throwing when global `crypto` lacks
      `randomUUID` (component regression test — would have caught the original bug)
- [ ] `eslint .` rejects a direct `crypto.randomUUID` access anywhere except `src/lib/uuid-utils.ts`
- [ ] `cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run` all green
- [ ] Manual dogfood: showcase run over a LAN-IP HTTP origin completes; no white screen;
      "Recent runs" strip shows the new entry (documented step per umbrella risk row)

## All Needed Context

### Documentation & References

```yaml
# MUST READ — secure-context semantics (the entire bug)
- url: https://developer.mozilla.org/en-US/docs/Web/API/Crypto/randomUUID
  why: "Secure context: This feature is available only in secure contexts (HTTPS)" — the
       method is literally undefined on the Crypto object otherwise; that is why the call
       throws TypeError (not a permission error).

- url: https://developer.mozilla.org/en-US/docs/Web/API/Crypto/getRandomValues
  why: getRandomValues is NOT marked secure-context-only — it is available on plain-HTTP
       origins, which is what makes it the correct fallback entropy source (cryptographically
       strong, unlike Math.random).

- url: https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts
  why: localhost / 127.0.0.1 count as secure contexts even over HTTP — explains why the bug
       only reproduces via a LAN IP and why local dev never caught it.

# MUST READ — codebase files
- file: frontend/src/components/demo/RunHistoryStrip.tsx
  why: The single call site (line 75, inside a render-phase setItems updater — that placement
       is WHY the throw unmounts the tree). Note the file's existing defensive ethos
       (SSR guards, swallowed quota errors) — the fix matches that spirit.

- file: frontend/src/components/demo/RunHistoryStrip.test.tsx
  why: The suite to extend. Style to mirror: describe/it, @testing-library/react render,
       beforeEach/afterEach localStorage cleanup, shared `summary` fixture (lines 17-25).

- file: frontend/src/lib/api.test.ts
  why: The house pattern for stubbing globals in vitest — `vi.stubGlobal(...)` + an
       `afterEach(() => vi.unstubAllGlobals())`. Reuse exactly this for stubbing `crypto`.

- file: frontend/src/lib/utils.ts
  why: Export style for src/lib — small named-export functions, no default exports.

- file: frontend/eslint.config.js
  why: Flat-config layout to extend. Note the existing per-path override block for
       src/components/ui/** — add the guard rule + the uuid-utils exemption as two more
       config objects in the same style.

- file: frontend/vitest.config.ts
  why: jsdom environment, colocated `src/**/*.test.{ts,tsx}` include, `@` alias — no setup
       file exists; do not add one for this.

- file: PRPs/PRP-reliability-E2-surface-fallback-failures.md
  why: Sibling epic of the same umbrella — house format for reliability PRPs (this file
       mirrors its structure).
```

### Current Codebase tree (relevant slice)

```bash
frontend/src/
├── components/demo/
│   ├── RunHistoryStrip.tsx        # line 75: id: crypto.randomUUID()   ← THE BUG
│   ├── RunHistoryStrip.test.tsx   # 5 existing cases, none non-secure-context
│   └── demo-step-card.tsx         # Date.now() for elapsed time only — NOT an id, leave alone
├── hooks/use-demo-pipeline.ts     # no id generation (verified)
└── lib/
    ├── utils.ts                   # cn() — named-export style to follow
    ├── api.test.ts                # vi.stubGlobal pattern to follow
    └── <17 other utils, almost all with colocated .test.ts>
frontend/eslint.config.js          # flat config; gets the no-restricted-properties guard
```

### Desired Codebase tree

```bash
frontend/src/lib/uuid-utils.ts        # NEW — safeRandomUUID() (named export)
frontend/src/lib/uuid-utils.test.ts   # NEW — 3 paths: native / getRandomValues / Math.random
frontend/src/components/demo/RunHistoryStrip.tsx       # MODIFIED — import + 1-line swap
frontend/src/components/demo/RunHistoryStrip.test.tsx  # MODIFIED — +1 regression case
frontend/eslint.config.js             # MODIFIED — guard rule + uuid-utils exemption
```

### Known Gotchas & Library Quirks

```typescript
// GOTCHA 1 — the bug does NOT reproduce naturally in vitest.
// jsdom's window.crypto (Node webcrypto) HAS randomUUID. Verified 2026-06-11:
//   cd frontend && node -e "const{JSDOM}=require('jsdom');const d=new JSDOM('');
//     console.log(typeof d.window.crypto.randomUUID)"   // -> "function"
// So every non-secure-context test MUST stub the global:
//   vi.stubGlobal('crypto', { getRandomValues: globalThis.crypto.getRandomValues.bind(globalThis.crypto) } as Crypto)
// and restore with vi.unstubAllGlobals() in afterEach (api.test.ts pattern).
// A test that "just calls the component" passes with or without the fix — worthless.

// GOTCHA 2 — TypeScript's lib.dom.d.ts types Crypto.randomUUID as NON-optional.
// `typeof crypto.randomUUID === 'function'` is statically "always true" to the checker but
// compiles fine (no strictness flag fires; @typescript-eslint/no-unnecessary-condition is
// not enabled in this repo). Do NOT use `crypto.randomUUID?.()` — optional-call on a
// non-optional member is also fine for TS but reads as if the types said it could be absent;
// the explicit typeof guard documents the runtime reality. Either compiles; use typeof.

// GOTCHA 3 — the v4 bit-twiddling is exact, not approximate:
//   bytes[6] = (bytes[6] & 0x0f) | 0x40   // version nibble -> 4
//   bytes[8] = (bytes[8] & 0x3f) | 0x80   // variant -> 10xxxxxx (8|9|a|b)
// Verified 2026-06-11 in Node 'node -e' (see PRP research log): output matches
//   /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
// Re-verify with the same one-liner if you change the byte math.

// GOTCHA 4 — eslint no-restricted-properties flags MEMBER ACCESS (crypto.randomUUID),
// not object-literal property definitions ({ randomUUID: vi.fn() } in test stubs is fine).
// The exemption override is needed only for src/lib/uuid-utils.ts itself.

// GOTCHA 5 — RunHistoryStrip appends DURING render (documented at lines 66-69 as the React
// "storing information from previous renders" pattern). Keep the fix to the one-line
// id: safeRandomUUID() swap — do NOT refactor the render-phase setState; that pattern is
// deliberate (react-hooks/set-state-in-effect) and out of scope.

// GOTCHA 6 — localhost IS a secure context even over plain HTTP. Manual verification MUST
// use a LAN IP (or any non-loopback hostname) to actually exercise the fallback path.

// GOTCHA 7 — repo has mixed CRLF/LF line endings with no policy. New files are fine (LF);
// for the three modified files check `git diff --stat` shows only the intended hunks, not a
// whole-file line-ending rewrite.

// GOTCHA 8 — frontend/tsconfig.app.json sets "noUncheckedIndexedAccess": true, so a
// Uint8Array index READ is `number | undefined` and `bytes[6] & 0x0f` is a TS2532 error.
// The blueprint uses `(bytes[6] ?? 0) & ...` for this reason — keep the ?? 0.
// ALSO: the root frontend/tsconfig.json is solution-style (files: [] + references), so
// `pnpm tsc --noEmit` type-checks ZERO files and exits 0 vacuously. The real type gate is
// `npx tsc -b` (what `pnpm build` runs) — and on current dev it already fails with
// pre-existing errors in untouched files (ai-models-panel.tsx, forecast-chart.tsx,
// job-picker.tsx, demand-utils.test.ts — noUncheckedIndexedAccess fallout). The bar for
// THIS PRP: `npx tsc -b` introduces NO NEW errors in the files this PRP touches. The hollow
// gate + pre-existing breakage deserves its own issue — flag it in the PR, don't fix here.
```

## Implementation Blueprint

### Data models and structure

No backend models, no schemas, no migrations. One pure function:

```typescript
// frontend/src/lib/uuid-utils.ts — complete implementation (it is small enough to spec fully)

/**
 * #332 — crypto.randomUUID() exists only in secure contexts (HTTPS or localhost).
 * On a plain-HTTP LAN origin (the showcase dogfood setup) it is undefined and a direct
 * call TypeErrors. crypto.getRandomValues is NOT secure-context-gated, so the fallback
 * keeps cryptographically-strong entropy; Math.random is a last resort for environments
 * with no Web Crypto at all (ids here are React keys / history ids, not security tokens).
 */
export function safeRandomUUID(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    // eslint-disable-next-line no-restricted-properties -- the one sanctioned call site
    return crypto.randomUUID()
  }
  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    const bytes = new Uint8Array(16)
    crypto.getRandomValues(bytes)
    bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x40 // version 4   (?? 0: Gotcha 8)
    bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80 // variant 10xx
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
  }
  // No Web Crypto at all — uniqueness only, not cryptographic strength.
  let uuid = ''
  for (let i = 0; i < 36; i++) {
    if (i === 8 || i === 13 || i === 18 || i === 23) uuid += '-'
    else if (i === 14) uuid += '4'
    else if (i === 19) uuid += (((Math.random() * 4) | 0) | 8).toString(16) // 8,9,a,b
    else uuid += ((Math.random() * 16) | 0).toString(16)
  }
  return uuid
}
```

(The inline `eslint-disable-next-line` is the ONLY exemption — do NOT also add a config-level
`'no-restricted-properties': 'off'` override for uuid-utils.ts. With the rule disabled at the
config level the inline directive becomes unused, and ESLint 9 flat config reports unused
disable directives as warnings by default — `pnpm lint` would no longer be clean.)

### Tasks (in order)

```yaml
Task 1:
CREATE frontend/src/lib/uuid-utils.ts:
  - CONTENT: exactly the implementation above (named export, no default — matches lib/utils.ts)
  - DOC COMMENT references issue #332 and the secure-context cause

Task 2:
CREATE frontend/src/lib/uuid-utils.test.ts:
  - MIRROR stubbing pattern from: frontend/src/lib/api.test.ts (vi.stubGlobal + afterEach unstub)
  - CASES (describe('safeRandomUUID')):
      1. "delegates to crypto.randomUUID when available" —
         vi.stubGlobal('crypto', { randomUUID: vi.fn(() => 'fixed-uuid') } as unknown as Crypto)
         expect(safeRandomUUID()).toBe('fixed-uuid')
      2. "falls back to getRandomValues v4 when randomUUID is missing (LAN-HTTP shape)" —
         stub crypto with ONLY getRandomValues (bind the real one:
         globalThis.crypto.getRandomValues.bind(globalThis.crypto));
         assert v4 regex /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
         AND two successive calls differ
      3. "falls back to Math.random v4 when crypto is entirely absent" —
         vi.stubGlobal('crypto', undefined); same regex + uniqueness assertions
  - GOTCHA: case 2/3 are the tests that fail on the unfixed direct-call code path — they are
    the spec for the fallback

Task 3:
MODIFY frontend/src/components/demo/RunHistoryStrip.tsx:
  - ADD import: import { safeRandomUUID } from '@/lib/uuid-utils'
  - FIND: "id: crypto.randomUUID()," (line 75)
  - REPLACE with: "id: safeRandomUUID(),"
  - PRESERVE everything else (render-phase append pattern is deliberate — Gotcha 5)

Task 4:
MODIFY frontend/src/components/demo/RunHistoryStrip.test.tsx:
  - ADD regression case to the existing describe('RunHistoryStrip'):
      "appends a history entry without crashing when crypto.randomUUID is unavailable (#332)"
      — vi.stubGlobal('crypto', { getRandomValues: globalThis.crypto.getRandomValues.bind(globalThis.crypto) } as unknown as Crypto)
        BEFORE render (capture the real getRandomValues reference first);
      — render(<RunHistoryStrip onReplay={() => {}} summary={summary} scenario="showcase_rich" />)
        must not throw;
      — assert localStorage entry exists, items[0].id matches the v4 regex;
      — vi.unstubAllGlobals() in afterEach (extend the existing afterEach)
  - REUSE the existing `summary` fixture (lines 17-25)
  - VERIFY-IT-BITES: `git stash` the Task-3 change once and confirm this test fails with
    "crypto.randomUUID is not a function", then unstash

Task 5:
MODIFY frontend/eslint.config.js:
  - APPEND one config object after the existing src/components/ui override, same style:
      {
        // #332 — crypto.randomUUID is undefined outside secure contexts (plain-HTTP LAN).
        files: ['**/*.{ts,tsx}'],
        rules: {
          'no-restricted-properties': [
            'error',
            {
              object: 'crypto',
              property: 'randomUUID',
              message:
                'crypto.randomUUID is undefined outside secure contexts (plain-HTTP LAN origins). Use safeRandomUUID() from @/lib/uuid-utils instead. (#332)',
            },
          ],
        },
      },
  - The single sanctioned call site inside uuid-utils.ts uses the inline
    eslint-disable-next-line from Task 1 — do NOT add a config-level off-override for that
    file (it would make the inline directive unused → unused-disable-directive warning).
  - VERIFY-IT-BITES: temporarily revert Task 3's swap (or add `const x = crypto.randomUUID` in
    a scratch file) and confirm `pnpm lint` fails with the message above, then restore

Task 6:
RUN validation gates (Level 1-2 below); then manual dogfood (Level 3).
```

### Integration Points

```yaml
BACKEND:   none — zero Python changes, no migration, no docs/_base contract change
CONFIG:    frontend/eslint.config.js only (Task 5)
DOCS:      none required; optional 1-line note in docs/_base/RUNBOOKS.md Showcase incident
           list is NOT needed (the incident ceases to exist once fixed)
GIT:
  branch:  fix/ui-safe-uuid-non-secure-context   (off dev; type/kebab, ≤50 chars)
  commits: fix(ui): avoid crypto.randomUUID crash on lan http showcase (#332)
           # the PRP file itself lands as: docs(repo): track reliability E3 prp for safe uuid fallback (#332)
           # (mirrors 7c57641 "docs(repo): track reliability E2 prp ..." precedent)
```

## Validation Loop

### Level 1: Syntax & Style (frontend gates)

```bash
cd frontend
pnpm tsc --noEmit        # the documented repo gate — but VACUOUS here (solution-style
                         # tsconfig type-checks zero files; Gotcha 8). Run it for the record.
npx tsc -b 2>&1 | grep uuid-utils   # the REAL check for this PRP: no NEW errors in touched
                         # files (tsc -b already fails on dev for pre-existing, unrelated
                         # files — see Gotcha 8; do not fix those here)
pnpm lint                # must pass WITH the new rule; see Task 5 verify-it-bites
```

### Level 2: Unit Tests

```bash
cd frontend && pnpm test --run
# Expected: uuid-utils.test.ts 3 cases green, RunHistoryStrip.test.tsx 6 cases green
# (5 existing + 1 regression), zero regressions elsewhere.
# If pnpm itself fails with "cannot execute binary file" (WSL IntxLNK corruption):
#   rm -rf node_modules && corepack enable pnpm && pnpm install && pnpm rebuild esbuild
```

### Level 3: Real-browser verification (the umbrella-mandated dogfood)

```bash
# The bug ONLY manifests on a non-loopback HTTP origin (Gotcha 6). Two tiers:

# 3a — quick: serve Vite LAN-reachable, verify the context shape from a real browser.
cd frontend && ./node_modules/.bin/vite --host 0.0.0.0   # (bypasses pnpm 11 depsStatusCheck)
# Playwright via native Python + snap Chromium (Playwright MCP / `playwright install`
# both fail on this host — see memory note; executable_path=/snap/bin/chromium):
#   page.goto("http://<lan-ip>:5173/showcase")
#   assert page.evaluate("window.isSecureContext") is False
#   assert page.evaluate("typeof crypto.randomUUID") == "undefined"
#   page reaches the Showcase UI with no console TypeError

# 3b — full: end-to-end completion over LAN HTTP (backend must also be reachable from the
# browser's origin — use the docker-compose.lan.yml override pattern or point frontend/.env
# VITE_API_BASE_URL at http://<lan-ip>:8123 while uvicorn binds 0.0.0.0).
# Run demo_minimal from the page; on pipeline_complete expect:
#   - NO white screen, no console TypeError
#   - "Recent runs" strip appears with the new entry (PASS + wall-clock)
#   - localStorage 'forecastlab.showcase.runs.v1' entry id matches the v4 regex
```

### Level 4: Backend gates untouched (sanity)

```bash
# No app/ changes, but CI runs everything — confirm nothing leaks:
uv run ruff check . && uv run mypy app/ && uv run pyright app/ \
  && uv run pytest -v -m "not integration"
```

## Final Validation Checklist

- [ ] `cd frontend && pnpm tsc --noEmit` — clean (vacuous; for the record) AND `npx tsc -b`
      reports zero errors in the files this PRP touches (Gotcha 8 — pre-existing errors in
      unrelated files are out of scope; flag them in the PR body)
- [ ] `cd frontend && pnpm lint` — clean, AND the rule bites on a planted `crypto.randomUUID` access
- [ ] `cd frontend && pnpm test --run` — all green, including the two new fallback specs and the
      component regression (which fails when Task 3 is reverted — proven once during Task 4)
- [ ] Manual LAN-HTTP dogfood done and described in the PR body (screenshot or console excerpt
      of `isSecureContext=false` + completed run)
- [ ] `git diff --stat` shows surgical hunks only (no line-ending rewrites — Gotcha 7)
- [ ] Commits formatted `fix(ui): ... (#332)`; no AI co-author trailer; branch off `dev`
- [ ] Backend gates green (no accidental `app/` or `uv.lock` churn in the PR — note the working
      tree currently has an unrelated dirty `uv.lock`; do NOT sweep it into this branch)

---

## Anti-Patterns to Avoid

- ❌ Don't add `uuid`/`nanoid` as a dependency for one call site — the 20-line util is the fix
- ❌ Don't "fix" by gating on `window.isSecureContext` — feature-detect the function itself;
  secure context is the *cause*, the absent function is the *fact*
- ❌ Don't use `Math.random` as the primary fallback — `getRandomValues` is available in
  non-secure contexts and strictly better; Math.random is last-resort only
- ❌ Don't refactor RunHistoryStrip's render-phase append while you're in there (Gotcha 5)
- ❌ Don't write the component regression test without stubbing `crypto` — jsdom has
  `randomUUID`, so an unstubbed test passes against the broken code (Gotcha 1)
- ❌ Don't skip the LAN-IP manual check by testing on `localhost` — localhost is a secure
  context and proves nothing (Gotcha 6)

## Confidence Score: 9/10

One-pass implementation is highly likely: single verified call site, complete helper spec
inline, verified byte-math, exact test stubbing recipe with the jsdom trap documented, and a
lint guard with a verify-it-bites step. The 1-point deduction is for the Level-3 dogfood,
which depends on host/LAN environment state (Vite binding, backend reachability from the LAN
origin) rather than anything in the diff itself.
