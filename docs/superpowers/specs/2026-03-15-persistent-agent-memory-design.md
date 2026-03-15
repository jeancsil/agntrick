# Design Spec: Persistent Agent Memory with SqliteSaver

## 1. Overview
The goal is to provide persistent conversation memory for all agents in the `agntrick` ecosystem by integrating `langgraph-checkpoint-sqlite`. This ensures that agents (including those used in `agntrick-whatsapp`) maintain context across sessions and process restarts.

## 2. Goals
- Replace `InMemorySaver` with `SqliteSaver` in `AgentBase` and `WhatsAppRouterAgent`.
- Centralize checkpointer management in `agntrick-storage`.
- Ensure `context_id` is correctly stored in `scheduled_tasks` and `notes`.
- Maintain high test coverage with new persistence-focused tests.

## 3. Architecture

### 3.1. Storage Layer (`agntrick-storage`)
- **Dependency:** Add `langgraph-checkpoint-sqlite` to `packages/agntrick-storage/pyproject.toml`.
- **`Database` class Enhancement:**
    - Add `get_checkpointer()` method returning a `SqliteSaver` or `AsyncSqliteSaver`.
    - Ensure it uses the existing SQLite connection/path.
- **Repositories Update:**
    - `TaskRepository.save`: Include `context_id` in `INSERT` query.
    - `TaskRepository._row_to_task`: Ensure `context_id` is read.
    - `NoteRepository.save`: Include `context_id` in `INSERT` query.
    - `NoteRepository._row_to_note`: Ensure `context_id` is read.

### 3.2. Core Agent Layer (`agntrick`)
- **`AgentBase` class Enhancement:**
    - Modify `__init__` to accept an optional `checkpointer`.
    - Update `_ensure_initialized` to use the provided `checkpointer` (defaulting to `InMemorySaver` only if persistence is not configured).
    - Use `self._thread_id` as the default `thread_id` in LangGraph config.

### 3.3. WhatsApp Integration (`agntrick-whatsapp`)
- **`WhatsAppRouterAgent` class Enhancement:**
    - In `start()`, initialize a shared `AsyncSqliteSaver` using the `Database` instance.
    - In `_get_or_create_graph()`, inject this shared checkpointer into `create_agent`.
    - Ensure `incoming.sender_id` is passed as `thread_id` to `graph.ainvoke`.
    - Update `_handle_note` and `_handle_schedule` to pass `sender_id` as `context_id` to the repositories.

## 4. Implementation Details

### 4.1. SQLite Migration
The `Database._init_schema` already contains migration logic for `context_id`. I will verify it runs correctly and add any missing indexes if needed.

### 4.2. Async Considerations
`langgraph-checkpoint-sqlite` provides both synchronous and asynchronous savers. Since `agntrick` is largely async, `AsyncSqliteSaver` is preferred where appropriate, especially in the WhatsApp router.

## 5. Testing & Validation

### 5.1. Unit Tests
- Test `Database.get_checkpointer()` returns a valid instance.
- Test `TaskRepository` and `NoteRepository` correctly persist and retrieve `context_id`.

### 5.2. Integration Tests
- **Persistence Test:**
    1. Initialize an agent with a `SqliteSaver`.
    2. Send a message: "My name is Jean."
    3. Close the agent and database connection.
    4. Re-initialize a new agent instance with the *same* database and `thread_id`.
    5. Send a message: "What is my name?"
    6. Verify the response is "Jean."

## 6. Documentation
- Update `docs/mcp-servers.md` or create `docs/persistence.md` explaining how to configure persistent memory.
- Document the requirement of `langgraph-checkpoint-sqlite`.
