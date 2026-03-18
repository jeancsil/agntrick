# Refactor: Consolidate Storage Logic and Remove Duplication

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the duplicated storage logic in `agntrick-whatsapp` and use the centralized `agntrick-storage` package as the single source of truth.

**Architecture:** 
1. Update `agntrick-whatsapp` imports to point to `agntrick_storage`.
2. Delete the redundant `packages/agntrick-whatsapp/src/agntrick_whatsapp/storage/` directory.
3. Simplify `agntrick-whatsapp` dependencies.

**Tech Stack:** Python, `agntrick-storage`.

---

## Chunk 1: Preparation and Import Refactoring

### Task 1: Update agntrick-whatsapp Dependencies

**Files:**
- Modify: `packages/agntrick-whatsapp/pyproject.toml`

- [ ] **Step 1: Ensure `agntrick-storage` is in dependencies**
- [ ] **Step 2: Remove redundant `langgraph-checkpoint-sqlite` (it's in `agntrick-storage`)**
- [ ] **Step 3: Commit**
```bash
git add packages/agntrick-whatsapp/pyproject.toml
git commit -m "chore(whatsapp): update dependencies to use agntrick-storage"
```

### Task 2: Refactor Imports in WhatsAppRouterAgent

**Files:**
- Modify: `packages/agntrick-whatsapp/src/agntrick_whatsapp/router.py`

- [ ] **Step 1: Update imports from `agntrick_whatsapp.storage` to `agntrick_storage`**
- [ ] **Step 2: Verify `WhatsAppRouterAgent` still correctly uses `Database`, `NoteRepository`, etc.**
- [ ] **Step 3: Commit**
```bash
git add packages/agntrick-whatsapp/src/agntrick_whatsapp/router.py
git commit -m "refactor(whatsapp): use centralized agntrick-storage in router"
```

---

## Chunk 2: Cleanup and Verification

### Task 3: Remove Duplicated Storage Code

**Files:**
- Delete: `packages/agntrick-whatsapp/src/agntrick_whatsapp/storage/`

- [ ] **Step 1: Search for any other internal usages of `agntrick_whatsapp.storage`**
- [ ] **Step 2: Delete the `storage` directory**
- [ ] **Step 3: Commit**
```bash
git rm -r packages/agntrick-whatsapp/src/agntrick_whatsapp/storage/
git commit -m "chore(whatsapp): remove duplicated storage module"
```

### Task 4: Final Verification

- [ ] **Step 1: Run WhatsApp agent tests (if any)**
Run: `pytest packages/agntrick-whatsapp/tests/`
- [ ] **Step 2: Run storage tests to ensure core is still healthy**
Run: `pytest packages/agntrick-storage/tests/`
- [ ] **Step 3: Verify the WhatsApp agent can still start (informational)**
