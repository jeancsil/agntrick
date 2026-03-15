"""Repository layer for database access."""

from agntrick.storage.repositories.note_repository import NoteRepository
from agntrick.storage.repositories.task_repository import TaskRepository

__all__ = ["NoteRepository", "TaskRepository"]
