"""Repository for scheduled tasks."""

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agntrick.storage.database import Database
    from agntrick.storage.models import ScheduledTask
else:
    from agntrick.storage.models import TaskStatus

logger = logging.getLogger(__name__)


class TaskRepository:
    """Repository for managing scheduled tasks in the database."""

    def __init__(self, db: "Database") -> None:
        """Initialize the repository.

        Args:
            db: Database connection instance.
        """
        self._db = db

    def save(self, task: "ScheduledTask") -> "ScheduledTask":
        """Save a task to the database.

        Args:
            task: Task to save.

        Returns:
            The saved task.
        """
        conn = self._db.connection
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO scheduled_tasks
            (id, action_type, action_agent, action_prompt, context_id, execute_at,
             cron_expression, status, created_at, completed_at, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.id,
                task.action_type.value,
                task.action_agent,
                task.action_prompt,
                task.context_id,
                task.execute_at,
                task.cron_expression,
                task.status.value,
                task.created_at,
                task.completed_at,
                task.error_message,
            ),
        )
        conn.commit()
        logger.debug(f"Saved task: {task.id}")
        return task

    def get_by_id(self, task_id: str) -> "ScheduledTask | None":
        """Get a task by ID.

        Args:
            task_id: Task ID.

        Returns:
            Task instance or None if not found.
        """
        conn = self._db.connection
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM scheduled_tasks WHERE id = ?",
            (task_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_task(dict(row))

    def get_due_tasks(self) -> list["ScheduledTask"]:
        """Get all pending tasks that are due for execution.

        Returns:
            List of due tasks.
        """
        conn = self._db.connection
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM scheduled_tasks
            WHERE status = ? AND execute_at <= ?
            ORDER BY execute_at ASC
            """,
            (TaskStatus.PENDING.value, time.time()),
        )
        return [self._row_to_task(dict(row)) for row in cursor.fetchall()]

    def update_status(
        self,
        task_id: str,
        status: str | TaskStatus,
        completed_at: float | None = None,
        error_message: str | None = None,
    ) -> bool:
        """Update task status.

        Args:
            task_id: Task ID.
            status: New status value (string or TaskStatus enum).
            completed_at: Optional completion timestamp.
            error_message: Optional error message.

        Returns:
            True if updated, False if not found.
        """
        if isinstance(status, TaskStatus):
            status = status.value

        conn = self._db.connection
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE scheduled_tasks
            SET status = ?,
                completed_at = COALESCE(?, completed_at),
                error_message = ?
            WHERE id = ?
            """,
            (status, completed_at, error_message, task_id),
        )
        conn.commit()
        updated = cursor.rowcount > 0
        if updated:
            logger.debug(f"Updated task {task_id} status to {status}")
        return updated

    def _row_to_task(self, row: dict[str, object]) -> "ScheduledTask":
        """Convert database row to ScheduledTask.

        Args:
            row: Database row as dictionary.

        Returns:
            ScheduledTask instance.
        """
        from agntrick.storage.models import ScheduledTask

        return ScheduledTask.from_db_row(row)
