# Phase Completion Flow

A phase lezárási munkafolyamat a ForecastLabAI projekthez.

---

## Phase Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│                        PHASE LIFECYCLE                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. DEVELOPMENT (feat/* → dev)                                  │
│     └── Feature branches merged to dev                          │
│                                                                 │
│  2. INTEGRATION (dev → main)                                    │
│     └── All features complete, merge dev to main                │
│                                                                 │
│  3. RELEASE (release-please)                                    │
│     └── Automated version bump + GitHub Release                 │
│                                                                 │
│  4. DOCUMENTATION                                               │
│     └── Update PHASE-index.md, phase docs                       │
│                                                                 │
│  5. SNAPSHOT (main → phase-N)                                   │
│     └── Create protected branch + audit tag                     │
│                                                                 │
│  6. SYNC (phase-N → dev)                                        │
│     └── Sync dev with main for next phase                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Részletes Lépések

### 1. Feature Complete - Dev → Main

```bash
# Ellenőrizd hogy minden feature merged dev-be
git checkout dev
git pull origin dev

# PR létrehozása main-be
gh pr create --base main --head dev \
  --title "feat(phase-N): complete Phase N implementation" \
  --body "## Summary
- Feature 1
- Feature 2
- Feature 3

## Test plan
- [x] All tests passing
- [x] Type checks green
- [x] Lint checks green"

# CI ellenőrzés és merge
gh pr checks <PR_NUMBER> --watch
gh pr merge <PR_NUMBER> --squash
```

### 2. Release

```bash
# Várd meg a release-please PR-t
gh pr list --label "autorelease: pending"

# Trigger CI ha szükséges
git checkout <release-branch>
git commit --allow-empty -m "chore: trigger CI"
git push

# Merge release PR (review szükséges)
gh pr merge <PR_NUMBER> --squash --delete-branch

# Ellenőrizd a release-t
gh release view v0.X.Y
```

### 3. Dokumentáció Frissítése

```bash
# Checkout main
git checkout main
git pull origin main

# Hozz létre docs branchet
git checkout -b docs/phase-N-completed

# Frissítsd a dokumentációt:
# - docs/PHASE-index.md (status: Completed)
# - docs/PHASE/N-PHASE_NAME.md (status, release info)

# PR és merge
gh pr create --base main --title "docs: mark Phase N as completed"
gh pr merge <PR_NUMBER> --squash --delete-branch
```

### 4. Phase Snapshot

```bash
# Frissítsd main-t
git checkout main
git pull origin main

# Hozd létre a phase branchet MAIN-ről
git checkout -b phase-N
git push origin phase-N

# Várj a phase-snapshot.yml workflow-ra
gh run list --workflow=phase-snapshot.yml --limit 1
gh run watch <RUN_ID>

# Ellenőrizd a taget
git fetch --tags
git tag -l "phase-N-*"
```

### 5. Dev Szinkronizálás

```bash
# Szinkronizáld dev-et a phase branch-ről
git checkout dev
git reset --hard phase-N
git push origin dev --force

# VAGY PR-rel (biztonságosabb)
gh pr create --base dev --head phase-N \
  --title "sync: update dev from phase-N"
```

---

## Phase Snapshot Workflow

A `phase-snapshot.yml` automatikusan:

1. **Full Validation**
   - Lint check
   - Type check (MyPy + Pyright)
   - Migration check
   - All tests (unit + integration)

2. **Create Audit Snapshot**
   - Generate metadata JSON
   - Collect validation results
   - Create markdown report
   - Upload audit artifact
   - Create annotated tag: `phase-N-snapshot-YYYYMMDD-<sha>`

---

## Branch Protection

A `phase-*` branchek automatikusan védettek:
- No force push
- No deletion
- Serves as audit trail

---

## Checklist: Phase Completion

```markdown
## Phase N Completion Checklist

### Development
- [ ] All PRPs implemented
- [ ] All features merged to dev
- [ ] All tests passing

### Integration
- [ ] Dev merged to main
- [ ] Release PR merged
- [ ] GitHub Release created (vX.Y.Z)

### Documentation
- [ ] PHASE-index.md updated (status: Completed)
- [ ] docs/PHASE/N-*.md updated
- [ ] Version history entry added

### Snapshot
- [ ] phase-N branch created from main
- [ ] phase-snapshot workflow passed
- [ ] Annotated tag created
- [ ] Audit artifact uploaded

### Sync
- [ ] Dev synced with main/phase-N
- [ ] Ready for next phase
```

---

## Példa: Phase 1 → Phase 2 Átmenet

```bash
# Phase 1 lezárva, Phase 2 kezdése

# 1. Ellenőrizd hogy phase-1 rendben van
git checkout phase-1
git log --oneline -3

# 2. Dev szinkronizálva van
git checkout dev
git log --oneline -3  # Ugyanaz mint phase-1

# 3. Kezdd Phase 2-t
git checkout -b feat/prp-3-ingest-layer
# ... fejlesztés ...
```

---

## Hibaelhárítás

### Phase branch behind main
```bash
# Töröld és hozd újra létre main-ről
git push origin --delete phase-N
git checkout main && git pull
git checkout -b phase-N
git push origin phase-N
```

### Dev diverged from main
```bash
# Reset dev to main
git checkout dev
git reset --hard origin/main
git push origin dev --force
```

### Régi phase tag törlése
```bash
# Töröld a remote taget
git push origin --delete phase-N-snapshot-YYYYMMDD-<sha>

# Töröld a local taget
git tag -d phase-N-snapshot-YYYYMMDD-<sha>
```
