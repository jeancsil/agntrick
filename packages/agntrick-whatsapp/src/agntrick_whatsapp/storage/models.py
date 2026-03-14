"""Pydantic models for scheduled tasks and notes."""

import logging
from datetime import datetime, UTC
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    """Task action types."""

    RUN_AGENT = "run_agent"
    SEND_MESSAGE = "send_message"


class TaskStatus(str, Enum):
    """Task execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ScheduledTask(BaseModel):
    """A scheduled task for execution.

    Attributes:
        id: Unique task identifier.
        action_type: Type of action (run_agent or send_message).
        action_agent: Agent name for run_agent actions.
        action_prompt: Prompt for run_agent actions.
        execute_at: Unix timestamp for next execution.
        cron_expression: Optional cron expression for recurring tasks.
        status: Current task status.
        created_at: Unix timestamp when task was created.
        completed_at: Unix timestamp when task completed (if applicable).
        error_message: Error message if task failed.
        metadata: Optional metadata (e.g., sender_id for reminders).
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    action_type: TaskType
    action_agent: str | None = None
    action_prompt: str | None = None
    execute_at: float
    cron_expression: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = Field(default_factory=lambda: datetime.now(UTC).timestamp())
    completed_at: float | None = None
    error_message: str | None = None
    metadata: dict[str, Any] | None = None

    def to_db_row(self) -> dict[str, Any]:
        """Convert to database row format.

        Returns:
            Dictionary suitable for database insertion.
        """
        return {
            "id": self.id,
            "action_type": self.action_type.value,
            "action_agent": self.action_agent,
            "action_prompt": self.action_prompt,
            "execute_at": self.execute_at,
            "cron_expression": self.cron_expression,
            "status": self.status.value,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "ScheduledTask":
        """Create from database row.

        Args:
            row: Dictionary representing a database row.

        Returns:
            ScheduledTask instance.
        """
        return cls(
            id=row["id"],
            action_type=TaskType(row["action_type"]),
            action_agent=row["action_agent"],
            action_prompt=row["action_prompt"],
            execute_at=row["execute_at"],
            cron_expression=row["cron_expression"],
            status=TaskStatus(row["status"]),
            created_at=row["created_at"],
            completed_at=row["completed_at"],
            error_message=row["error_message"],
            metadata=row.get("metadata"),
        )


class Note(BaseModel):
    """A simple note stored in the database.

    Attributes:
        id: Unique note identifier.
        content: Note content.
        created_at: Unix timestamp when note was created.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    content: str
    created_at: float = Field(default_factory=lambda: datetime.now(UTC).timestamp())

    def to_db_row(self) -> dict[str, Any]:
        """Convert to database row format.

        Returns:
            Dictionary suitable for database insertion.
        """
        return {
            "id": self.id,
            "content": self.content,
            "created_at": self.created_at,
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "Note":
        """Create from database row.

        Args:
            row: Dictionary representing a database row.

        Returns:
            Note instance.
        """
        return cls(
            id=row["id"],
            content=row["content"],
            created_at=row["created_at"],
        )
