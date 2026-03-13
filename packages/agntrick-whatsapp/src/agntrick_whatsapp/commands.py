"""Command parsing and routing for WhatsApp agent.

This module provides a clean command parsing architecture using:
- Dataclasses for type-safe command representation
- A dedicated parser class with single responsibility
- Match-based dispatch for routing
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class CommandType(Enum):
    """Enumeration of all supported command types."""
    DEFAULT = "default"
    LEARN = "learn"
    YOUTUBE = "youtube"
    SCHEDULE = "schedule"
    REMIND = "remind"
    NOTE = "note"
    NOTES = "notes"
    HELP = "help"


@dataclass
class BaseCommand:
    """Base class for all commands."""
    command_type: CommandType


@dataclass
class QueryCommand(BaseCommand):
    """Commands that have a text query (learn, youtube, default)."""
    query: str


@dataclass
class ScheduleCommand(BaseCommand):
    """Schedule command with time, optional agent, and optional prompt."""
    time_str: str
    agent: str | None = None
    prompt: str | None = None


@dataclass
class RemindCommand(BaseCommand):
    """Remind command with time and optional prompt."""
    time_str: str
    prompt: str | None = None


@dataclass
class NoteCommand(BaseCommand):
    """Note command with content."""
    content: str


@dataclass
class NotesCommand(BaseCommand):
    """Notes command to list all notes."""
    pass


@dataclass
class HelpCommand(BaseCommand):
    """Help command to show available commands."""
    pass


# Type alias for all command types
Command = QueryCommand | ScheduleCommand | RemindCommand | NoteCommand | NotesCommand | HelpCommand


class CommandParser:
    """Parses WhatsApp messages into structured Command objects.

    This class encapsulates all command parsing logic with a clean,
    testable interface. It uses a single-pass parsing approach with
    clear separation between command detection and parameter extraction.
    """

    # Command prefix mappings for O(1) lookup
    COMMAND_PREFIXES: dict[str, CommandType] = {
        "/learn": CommandType.LEARN,
        "/youtube": CommandType.YOUTUBE,
        "/schedule": CommandType.SCHEDULE,
        "/remind": CommandType.REMIND,
        "/note": CommandType.NOTE,
        "/notes": CommandType.NOTES,
        "/help": CommandType.HELP,
    }

    def parse(self, text: str) -> Command:
        """Parse message text into a Command object.

        Args:
            text: The raw message text from WhatsApp.

        Returns:
            A Command object representing the parsed command.
        """
        text = text.strip()
        lower_text = text.lower()

        # Check for known command prefixes
        for prefix, cmd_type in self.COMMAND_PREFIXES.items():
            if lower_text == prefix or lower_text.startswith(prefix + " "):
                return self._parse_command(cmd_type, text[len(prefix):].strip(), text)

        # Default: treat as a general query
        return QueryCommand(command_type=CommandType.DEFAULT, query=text)

    def _parse_command(self, cmd_type: CommandType, args: str, original_text: str) -> Command:
        """Dispatch to specific parser based on command type.

        Args:
            cmd_type: The detected command type.
            args: The text after the command prefix.
            original_text: The original full message text.

        Returns:
            A Command object with parsed parameters.
        """
        match cmd_type:
            case CommandType.LEARN:
                return self._parse_learn(args)
            case CommandType.YOUTUBE:
                return self._parse_youtube(args)
            case CommandType.SCHEDULE:
                return self._parse_schedule(args)
            case CommandType.REMIND:
                return self._parse_remind(args)
            case CommandType.NOTE:
                return self._parse_note(args)
            case CommandType.NOTES:
                return NotesCommand(command_type=CommandType.NOTES)
            case CommandType.HELP:
                return HelpCommand(command_type=CommandType.HELP)
            case _:
                return QueryCommand(command_type=CommandType.DEFAULT, query=original_text)

    def _parse_learn(self, args: str) -> QueryCommand:
        """Parse /learn command."""
        query = args if args else "What would you like to learn about? Please provide a topic."
        return QueryCommand(command_type=CommandType.LEARN, query=query)

    def _parse_youtube(self, args: str) -> QueryCommand:
        """Parse /youtube command."""
        query = args if args else "Please provide a YouTube URL or tell me what you'd like to know about a video."
        return QueryCommand(command_type=CommandType.YOUTUBE, query=query)

    def _parse_schedule(self, args: str) -> ScheduleCommand:
        """Parse /schedule command.

        Format: /schedule <time> <agent> [prompt]
        """
        if not args:
            return ScheduleCommand(
                command_type=CommandType.SCHEDULE,
                time_str="",
                agent=None,
                prompt="Usage: /schedule <time> <agent> [prompt]"
            )

        parts = args.split(maxsplit=2)
        time_str = parts[0]
        agent = parts[1] if len(parts) > 1 else None
        prompt = parts[2] if len(parts) > 2 else None

        return ScheduleCommand(
            command_type=CommandType.SCHEDULE,
            time_str=time_str,
            agent=agent,
            prompt=prompt
        )

    def _parse_remind(self, args: str) -> RemindCommand:
        """Parse /remind command with smart time extraction.

        Format: /remind <time> <prompt>

        Uses dateparser to find the longest parseable time prefix.
        """
        if not args:
            return RemindCommand(
                command_type=CommandType.REMIND,
                time_str="",
                prompt="Usage: /remind <time> <prompt>"
            )

        import dateparser

        words = args.split()
        best_time_str = words[0]
        best_prompt_start = 1

        # Find the longest parseable time prefix
        for i in range(1, len(words) + 1):
            candidate = " ".join(words[:i])
            if dateparser.parse(candidate) is not None:
                best_time_str = candidate
                best_prompt_start = i

        prompt = " ".join(words[best_prompt_start:]) if best_prompt_start < len(words) else None

        return RemindCommand(
            command_type=CommandType.REMIND,
            time_str=best_time_str,
            prompt=prompt
        )

    def _parse_note(self, args: str) -> NoteCommand:
        """Parse /note command."""
        content = args if args else "Please provide the note content."
        return NoteCommand(command_type=CommandType.NOTE, content=content)
