"""Repository layer for database access."""

from agntrick_storage.repositories.note_repository import NoteRepository
from agntrick_storage.repositories.task_repository import TaskRepository

__all__ = ["NoteRepository", "TaskRepository"]
