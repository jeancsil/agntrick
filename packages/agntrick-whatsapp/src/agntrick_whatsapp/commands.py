"""Command parsing and routing for WhatsApp agent.

This module provides a clean command parsing architecture using:
- Dataclasses for type-safe command representation
- A dedicated parser class with single responsibility
- Match-based dispatch for routing
"""

from dataclasses import dataclass
from enum import Enum


class CommandType(Enum):
    """Enumeration of all supported command types."""
    DEFAULT = "default"
    LEARN = "learn"
    YOUTUBE = "youtube"
    SCHEDULE = "schedule"
    SCHEDULES = "schedules"
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
class SchedulesCommand(BaseCommand):
    """Schedules command to list all scheduled tasks."""
    pass


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
Command = QueryCommand | ScheduleCommand | SchedulesCommand | RemindCommand | NoteCommand | NotesCommand | HelpCommand


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
        "/schedules": CommandType.SCHEDULES,
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
            case CommandType.SCHEDULES:
                return SchedulesCommand(command_type=CommandType.SCHEDULES)
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
        """Parse /schedule command with smart time extraction.

        Format: /schedule <time> <agent> [prompt]

        Uses dateparser and recurring pattern detection to find the time expression.
        Supports: "every day 8:00 am", "every day at 8:00 am", "tomorrow 4pm", etc.
        """
        if not args:
            return ScheduleCommand(
                command_type=CommandType.SCHEDULE,
                time_str="",
                agent=None,
                prompt="Usage: /schedule <time> <agent> [prompt]"
            )

        import re

        import dateparser

        words = args.split()
        best_time_str = words[0]
        best_time_end = 1

        # Pattern 1: "every day [at] HH:MM [am/pm]" - matches with or without "at"
        # Captures time with optional am/pm
        every_day_at_pattern = re.compile(
            r"^every\s+days?\s+(?:at\s+)?\d{1,2}(?::\d{2})?\s*(am|pm)?$",
            re.IGNORECASE
        )
        # Pattern 2: "every day [at] HH:MM" - without am/pm
        every_day_time_pattern = re.compile(
            r"^every\s+days?\s+(?:at\s+)?\d{1,2}(?::\d{2})?$",
            re.IGNORECASE
        )

        # Check for recurring patterns first (highest priority)
        for i in range(1, len(words) + 1):
            candidate = " ".join(words[:i])
            if every_day_at_pattern.match(candidate):
                # Check if next word is am/pm - if so, include it
                if i < len(words) and words[i].lower() in ("am", "pm"):
                    best_time_str = candidate + " " + words[i]
                    best_time_end = i + 1
                else:
                    best_time_str = candidate
                    best_time_end = i
                break
            # Also check if current candidate matches time pattern (without am/pm)
            # and next word is am/pm
            if every_day_time_pattern.match(candidate):
                if i < len(words) and words[i].lower() in ("am", "pm"):
                    best_time_str = candidate + " " + words[i]
                    best_time_end = i + 1
                    break

        # If no recurring pattern found, try dateparser for one-time expressions
        # Find the LONGEST valid time expression
        if best_time_end == 1:
            for i in range(len(words), 0, -1):  # Start from longest
                candidate = " ".join(words[:i])
                parsed = dateparser.parse(candidate)
                if parsed is not None:
                    # Verify this is a reasonable time expression
                    # (not something like "in 5 minutes bot" which dateparser incorrectly parses)
                    remaining = len(words) - i
                    # Accept if we have room for agent (at least 1 remaining word)
                    if remaining >= 1:
                        best_time_str = candidate
                        best_time_end = i
                        break
                    # Or if this uses all words (no agent/prompt)
                    if remaining == 0:
                        best_time_str = candidate
                        best_time_end = i
                        break

        # After time: next word is agent, rest is prompt
        remaining_words = words[best_time_end:]
        agent = remaining_words[0] if remaining_words else None
        prompt = " ".join(remaining_words[1:]) if len(remaining_words) > 1 else None

        return ScheduleCommand(
            command_type=CommandType.SCHEDULE,
            time_str=best_time_str,
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
