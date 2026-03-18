# Persistent Agent Memory Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable persistent conversation memory for all agents using `langgraph-checkpoint-sqlite`, ensuring context survives process restarts and is shared between CLI and WhatsApp.

**Architecture:** Centralize `SqliteSaver` management in `agntrick-storage`. Update `AgentBase` and `WhatsAppRouterAgent` to use this saver, mapping `context_id` to LangGraph's `thread_id`.

**Tech Stack:** `langgraph-checkpoint-sqlite`, `sqlite3`, `pydantic`.

---

## Chunk 1: agntrick-storage Enhancement

### Task 1: Update Dependencies and Database Class

**Files:**
- Modify: `packages/agntrick-storage/pyproject.toml`
- Modify: `packages/agntrick-storage/src/agntrick_storage/database.py`

- [ ] **Step 1: Add `langgraph-checkpoint-sqlite` to dependencies**
- [ ] **Step 2: Update `Database` class to support checkpointer**
    Add `get_checkpointer(self, is_async: bool = False)` method.
- [ ] **Step 3: Commit**
```bash
git add packages/agntrick-storage/pyproject.toml packages/agntrick-storage/src/agntrick_storage/database.py
git commit -m "feat(storage): add langgraph-checkpoint-sqlite dependency and Database.get_checkpointer"
```

### Task 2: Update Repositories for context_id Persistence

**Files:**
- Modify: `packages/agntrick-storage/src/agntrick_storage/repositories/task_repository.py`
- Modify: `packages/agntrick-storage/src/agntrick_storage/repositories/note_repository.py`

- [ ] **Step 1: Update `TaskRepository.save` to include `context_id`**
- [ ] **Step 2: Update `NoteRepository.save` to include `context_id`**
- [ ] **Step 3: Run existing storage tests**
Run: `pytest packages/agntrick-storage/tests/`
- [ ] **Step 4: Commit**
```bash
git add packages/agntrick-storage/src/agntrick_storage/repositories/
git commit -m "feat(storage): ensure context_id is persisted in task and note repositories"
```

---

## Chunk 2: agntrick Core Update

### Task 3: Update AgentBase for Persistence

**Files:**
- Modify: `src/agntrick/agent.py`

- [ ] **Step 1: Modify `AgentBase.__init__` to accept `checkpointer`**
- [ ] **Step 2: Update `AgentBase._ensure_initialized` to use provided checkpointer**
- [ ] **Step 3: Commit**
```bash
git add src/agntrick/agent.py
git commit -m "feat(core): support persistent checkpointers in AgentBase"
```

---

## Chunk 3: agntrick-whatsapp Integration

### Task 4: Update WhatsAppRouterAgent for Persistence

**Files:**
- Modify: `packages/agntrick-whatsapp/src/agntrick_whatsapp/router.py`

- [ ] **Step 1: Initialize `AsyncSqliteSaver` in `WhatsAppRouterAgent.start`**
- [ ] **Step 2: Inject checkpointer in `_get_or_create_graph`**
- [ ] **Step 3: Ensure `sender_id` is passed as `context_id` when saving notes/tasks**
- [ ] **Step 4: Commit**
```bash
git add packages/agntrick-whatsapp/src/agntrick_whatsapp/router.py
git commit -m "feat(whatsapp): enable persistent memory in WhatsAppRouterAgent"
```

---

## Chunk 4: Verification and Documentation

### Task 5: Persistence Integration Test

**Files:**
- Create: `packages/agntrick-storage/tests/test_persistence_integration.py`

- [ ] **Step 1: Write integration test for cross-session memory**
- [ ] **Step 2: Run verification test**
Run: `pytest packages/agntrick-storage/tests/test_persistence_integration.py`
- [ ] **Step 3: Commit**
```bash
git add packages/agntrick-storage/tests/test_persistence_integration.py
git commit -m "test: add integration test for persistent agent memory"
```

### Task 6: Documentation Update

**Files:**
- Create: `docs/persistence.md`
- Modify: `README.md`

- [ ] **Step 1: Create persistence documentation**
- [ ] **Step 2: Link from README**
- [ ] **Step 3: Commit**
```bash
git add docs/persistence.md README.md
git commit -m "docs: add agent memory persistence guide"
```
