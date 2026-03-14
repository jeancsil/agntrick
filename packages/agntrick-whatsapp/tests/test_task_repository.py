"""Unit tests for TaskRepository."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Mock agntrick module before importing
mock_agntrick = MagicMock()
mock_agntrick.constants = MagicMock()
mock_agntrick.constants.STORAGE_DIR = Path("/tmp/agntrick")
mock_agntrick.llm = MagicMock()
mock_agntrick.llm.get_default_model = lambda: "gpt-4"
mock_agntrick.mcp = MagicMock()
mock_agntrick.mcp.MCPProvider = MagicMock
mock_agntrick.registry = MagicMock()
mock_agntrick.registry.AgentRegistry = MagicMock
mock_agntrick.tools = MagicMock()
mock_agntrick.tools.YouTubeTranscriptTool = MagicMock

sys.modules["agntrick"] = mock_agntrick
sys.modules["agntrick.constants"] = mock_agntrick.constants
sys.modules["agntrick.llm"] = mock_agntrick.llm
sys.modules["agntrick.mcp"] = mock_agntrick.mcp
sys.modules["agntrick.registry"] = mock_agntrick.registry
sys.modules["agntrick.tools"] = mock_agntrick.tools

# Mock langchain modules
sys.modules["langchain.agents"] = MagicMock()
sys.modules["langchain_openai"] = MagicMock()
sys.modules["langgraph.checkpoint.memory"] = MagicMock()

from agntrick_whatsapp.storage.database import Database
from agntrick_whatsapp.storage.models import (
    ScheduledTask,
    TaskStatus,
    TaskType,
)
from agntrick_whatsapp.storage.repositories import TaskRepository


class TestTaskRepository:
    """Tests for TaskRepository."""

    @pytest.fixture
    def db_path(self):
        """Create a temporary database path."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            yield Path(f.name)

    @pytest.fixture
    def db(self, db_path):
        """Create a database instance."""
        return Database(db_path)

    @pytest.fixture
    def repo(self, db):
        """Create a task repository instance."""
        return TaskRepository(db)

    def test_save_task(self, repo):
        """Test saving a task to database."""
        task = ScheduledTask(
            id="task-1",
            action_type=TaskType.RUN_AGENT,
            action_agent="developer",
            action_prompt="test prompt",
            execute_at=1234567890.0,
            cron_expression="0 8 * * *",
            status=TaskStatus.PENDING,
        )
        saved = repo.save(task)
        assert saved.id == "task-1"

    def test_get_by_id(self, repo):
        """Test retrieving a task by ID."""
        task = ScheduledTask(
            id="task-2",
            action_type=TaskType.SEND_MESSAGE,
            action_prompt="reminder",
            execute_at=1234567890.0,
            status=TaskStatus.PENDING,
            metadata={"sender_id": "12345"},
        )
        repo.save(task)

        retrieved = repo.get_by_id("task-2")
        assert retrieved is not None
        assert retrieved.id == "task-2"
        assert retrieved.action_prompt == "reminder"
        assert retrieved.metadata == {"sender_id": "12345"}

    def test_get_by_id_not_found(self, repo):
        """Test retrieving non-existent task returns None."""
        retrieved = repo.get_by_id("non-existent")
        assert retrieved is None

    def test_get_due_tasks(self, repo):
        """Test retrieving due tasks."""
        import time

        now = time.time()

        # Create a past-due task
        past_task = ScheduledTask(
            id="past-task",
            action_type=TaskType.SEND_MESSAGE,
            action_prompt="past",
            execute_at=now - 3600,  # 1 hour ago
            status=TaskStatus.PENDING,
        )
        repo.save(past_task)

        # Create a future task
        future_task = ScheduledTask(
            id="future-task",
            action_type=TaskType.SEND_MESSAGE,
            action_prompt="future",
            execute_at=now + 3600,  # 1 hour from now
            status=TaskStatus.PENDING,
        )
        repo.save(future_task)

        # Create a completed task
        completed_task = ScheduledTask(
            id="completed-task",
            action_type=TaskType.SEND_MESSAGE,
            action_prompt="completed",
            execute_at=now - 7200,
            status=TaskStatus.COMPLETED,
        )
        repo.save(completed_task)

        due_tasks = repo.get_due_tasks()
        assert len(due_tasks) == 1
        assert due_tasks[0].id == "past-task"

    def test_update_status_to_completed(self, repo):
        """Test updating task status to completed."""
        task = ScheduledTask(
            id="task-3",
            action_type=TaskType.SEND_MESSAGE,
            action_prompt="test",
            execute_at=1234567890.0,
            status=TaskStatus.PENDING,
        )
        repo.save(task)

        updated = repo.update_status("task-3", TaskStatus.COMPLETED)
        assert updated is True

        retrieved = repo.get_by_id("task-3")
        assert retrieved.status == TaskStatus.COMPLETED

    def test_update_status_with_completed_at(self, repo):
        """Test updating status with completion timestamp."""
        import time

        task = ScheduledTask(
            id="task-4",
            action_type=TaskType.SEND_MESSAGE,
            action_prompt="test",
            execute_at=1234567890.0,
            status=TaskStatus.RUNNING,
        )
        repo.save(task)

        completed_at = time.time()
        updated = repo.update_status("task-4", TaskStatus.COMPLETED, completed_at=completed_at)
        assert updated is True

        retrieved = repo.get_by_id("task-4")
        assert retrieved.completed_at == completed_at

    def test_update_status_with_error_message(self, repo):
        """Test updating status with error message."""
        task = ScheduledTask(
            id="task-5",
            action_type=TaskType.SEND_MESSAGE,
            action_prompt="test",
            execute_at=1234567890.0,
            status=TaskStatus.RUNNING,
        )
        repo.save(task)

        error_msg = "Connection timeout"
        updated = repo.update_status("task-5", TaskStatus.FAILED, error_message=error_msg)
        assert updated is True

        retrieved = repo.get_by_id("task-5")
        assert retrieved.status == TaskStatus.FAILED
        assert retrieved.error_message == error_msg

    def test_update_execute_at(self, repo):
        """Test updating task execution time."""
        import time

        task = ScheduledTask(
            id="task-6",
            action_type=TaskType.SEND_MESSAGE,
            action_prompt="recurring task",
            execute_at=1234567890.0,
            cron_expression="0 8 * * *",
            status=TaskStatus.RUNNING,
        )
        repo.save(task)

        new_execute_at = time.time() + 86400  # Tomorrow
        updated = repo.update_execute_at("task-6", new_execute_at)
        assert updated is True

        retrieved = repo.get_by_id("task-6")
        assert retrieved.execute_at == new_execute_at

    def test_update_execute_at_not_found(self, repo):
        """Test updating execute_at for non-existent task."""
        updated = repo.update_execute_at("non-existent", 9999999999.0)
        assert updated is False

    def test_save_with_cron_expression(self, repo):
        """Test saving task with cron expression for recurring tasks."""
        task = ScheduledTask(
            id="recurring-task",
            action_type=TaskType.RUN_AGENT,
            action_agent="news",
            action_prompt="daily briefing",
            execute_at=1234567890.0,
            cron_expression="0 8 * * *",  # Daily at 8am
            status=TaskStatus.PENDING,
        )
        saved = repo.save(task)

        retrieved = repo.get_by_id("recurring-task")
        assert retrieved.cron_expression == "0 8 * * *"

    def test_save_with_metadata(self, repo):
        """Test saving task with metadata dictionary."""
        metadata = {"sender_id": "12345", "priority": "high"}
        task = ScheduledTask(
            id="task-with-meta",
            action_type=TaskType.SEND_MESSAGE,
            action_prompt="test",
            execute_at=1234567890.0,
            status=TaskStatus.PENDING,
            metadata=metadata,
        )
        repo.save(task)

        retrieved = repo.get_by_id("task-with-meta")
        assert retrieved.metadata == metadata
