# Refactor: Move Storage to agntrick Core

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the persistent storage logic from the standalone `agntrick-storage` package into the main `agntrick` core package. This allows `agntrick-whatsapp` to use it via its existing dependency on `agntrick` without duplication or PyPI issues.

**Architecture:**
1. Relocate `packages/agntrick-storage/src/agntrick_storage/` to `src/agntrick/storage/`.
2. Update all imports in `src/agntrick/`, `packages/agntrick-whatsapp/`, and tests.
3. Remove the `packages/agntrick-storage/` directory.
4. Consolidate dependencies in the main `pyproject.toml`.

**Tech Stack:** Python, `langgraph-checkpoint-sqlite`.

---

## Chunk 1: Relocation and Core Integration

### Task 1: Move Storage Files and Update Core Dependencies

**Files:**
- Create: `src/agntrick/storage/` (move files here)
- Modify: `pyproject.toml` (main)

- [ ] **Step 1: Move `packages/agntrick-storage/src/agntrick_storage/*` to `src/agntrick/storage/`**
- [ ] **Step 2: Update `pyproject.toml` (main) to include `langgraph-checkpoint-sqlite`, `dateparser`, and `croniter`**
- [ ] **Step 3: Commit relocation**
```bash
mkdir -p src/agntrick/storage/
cp -r packages/agntrick-storage/src/agntrick_storage/* src/agntrick/storage/
git add src/agntrick/storage/
git commit -m "refactor(core): move storage module to agntrick core"
```

### Task 2: Internal Import Refactoring (agntrick/storage)

**Files:**
- Modify all files in `src/agntrick/storage/`

- [ ] **Step 1: Update internal imports from `agntrick_storage` to `agntrick.storage`**
- [ ] **Step 2: Commit refactor**
```bash
# Example update in database.py, models.py, repositories/
git commit -m "refactor(core): update internal storage imports"
```

---

## Chunk 2: Interface Integration

### Task 3: Update WhatsApp Agent to Use Core Storage

**Files:**
- Modify: `packages/agntrick-whatsapp/src/agntrick_whatsapp/router.py`
- Modify: `packages/agntrick-whatsapp/pyproject.toml`

- [ ] **Step 1: Update imports from `agntrick_storage` to `agntrick.storage`**
- [ ] **Step 2: Remove `agntrick-storage` from `packages/agntrick-whatsapp/pyproject.toml`**
- [ ] **Step 3: Commit interface updates**
```bash
git add packages/agntrick-whatsapp/
git commit -m "refactor(whatsapp): use core storage instead of separate package"
```

---

## Chunk 3: Cleanup and Verification

### Task 4: Remove agntrick-storage Package

- [ ] **Step 1: Delete `packages/agntrick-storage/` directory**
- [ ] **Step 2: Commit deletion**
```bash
git rm -r packages/agntrick-storage/
git commit -m "chore: remove agntrick-storage package"
```

### Task 5: Relocate and Update Tests

**Files:**
- Move: `packages/agntrick-storage/tests/` to `tests/storage/`

- [ ] **Step 1: Move and update tests to point to `agntrick.storage`**
- [ ] **Step 2: Run all tests**
Run: `make test`
Run: `PYTHONPATH=src uv run pytest tests/storage/test_persistence_integration.py`
- [ ] **Step 3: Commit test relocation**
```bash
mkdir -p tests/storage/
mv packages/agntrick-storage/tests/* tests/storage/
git add tests/storage/
git commit -m "test: relocate and update storage tests"
```
