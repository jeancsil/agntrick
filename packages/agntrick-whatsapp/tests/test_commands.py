"""Unit tests for the command parsing module."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Mock agntrick module before importing agntrick_whatsapp
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

from agntrick_whatsapp.commands import (
    CommandParser,
    CommandType,
    HelpCommand,
    NoteCommand,
    NotesCommand,
    QueryCommand,
    RemindCommand,
    ScheduleCommand,
    SchedulesCommand,
)


class TestCommandParser:
    """Tests for the CommandParser class."""

    @pytest.fixture
    def parser(self):
        """Create a command parser instance."""
        return CommandParser()

    # === LEARN command tests ===
    def test_parse_learn_with_topic(self, parser):
        """Test parsing /learn with a topic."""
        result = parser.parse("/learn python async programming")
        assert isinstance(result, QueryCommand)
        assert result.command_type == CommandType.LEARN
        assert result.query == "python async programming"

    def test_parse_learn_uppercase(self, parser):
        """Test parsing /LEARN (case insensitive)."""
        result = parser.parse("/LEARN Python")
        assert isinstance(result, QueryCommand)
        assert result.command_type == CommandType.LEARN
        assert result.query == "Python"

    def test_parse_learn_mixed_case(self, parser):
        """Test parsing /LeArN (mixed case)."""
        result = parser.parse("/LeArN testing")
        assert isinstance(result, QueryCommand)
        assert result.command_type == CommandType.LEARN
        assert result.query == "testing"

    def test_parse_learn_without_topic(self, parser):
        """Test parsing /learn without a topic returns default message."""
        result = parser.parse("/learn")
        assert isinstance(result, QueryCommand)
        assert result.command_type == CommandType.LEARN
        assert "topic" in result.query.lower()

    # === YOUTUBE command tests ===
    def test_parse_youtube_with_url(self, parser):
        """Test parsing /youtube with a URL."""
        result = parser.parse("/youtube https://youtube.com/watch?v=abc123")
        assert isinstance(result, QueryCommand)
        assert result.command_type == CommandType.YOUTUBE
        assert "youtube.com" in result.query

    def test_parse_youtube_with_query(self, parser):
        """Test parsing /youtube with a search query."""
        result = parser.parse("/youtube how to bake a cake")
        assert isinstance(result, QueryCommand)
        assert result.command_type == CommandType.YOUTUBE
        assert result.query == "how to bake a cake"

    def test_parse_youtube_uppercase(self, parser):
        """Test parsing /YOUTUBE (case insensitive)."""
        result = parser.parse("/YOUTUBE video tutorial")
        assert isinstance(result, QueryCommand)
        assert result.command_type == CommandType.YOUTUBE
        assert result.query == "video tutorial"

    def test_parse_youtube_without_args(self, parser):
        """Test parsing /youtube without arguments returns default message."""
        result = parser.parse("/youtube")
        assert isinstance(result, QueryCommand)
        assert result.command_type == CommandType.YOUTUBE
        assert "URL" in result.query or "video" in result.query.lower()

    # === SCHEDULE command tests ===
    def test_parse_schedule_full(self, parser):
        """Test parsing /schedule with all arguments."""
        result = parser.parse("/schedule tomorrow at 9am developer review the code")
        assert isinstance(result, ScheduleCommand)
        assert result.command_type == CommandType.SCHEDULE
        assert result.time_str == "tomorrow at 9am"
        assert result.agent == "developer"
        assert result.prompt == "review the code"

    def test_parse_schedule_minimal(self, parser):
        """Test parsing /schedule with time and agent only."""
        result = parser.parse("/schedule tomorrow agent1")
        assert isinstance(result, ScheduleCommand)
        assert result.command_type == CommandType.SCHEDULE
        assert result.time_str == "tomorrow"
        assert result.agent == "agent1"
        assert result.prompt is None

    def test_parse_schedule_time_only(self, parser):
        """Test parsing /schedule with only time."""
        result = parser.parse("/schedule tomorrow")
        assert isinstance(result, ScheduleCommand)
        assert result.command_type == CommandType.SCHEDULE
        assert result.time_str == "tomorrow"
        assert result.agent is None
        assert result.prompt is None

    def test_parse_schedule_uppercase(self, parser):
        """Test parsing /SCHEDULE (case insensitive)."""
        result = parser.parse("/SCHEDULE friday bot task")
        assert isinstance(result, ScheduleCommand)
        assert result.command_type == CommandType.SCHEDULE

    def test_parse_schedule_without_args(self, parser):
        """Test parsing /schedule without arguments returns usage message."""
        result = parser.parse("/schedule")
        assert isinstance(result, ScheduleCommand)
        assert "Usage" in result.prompt

    def test_parse_schedule_every_day(self, parser):
        """Test parsing /schedule with 'every day' pattern."""
        result = parser.parse("/schedule every day at 8am news summarize headlines")
        assert isinstance(result, ScheduleCommand)
        assert result.command_type == CommandType.SCHEDULE
        assert "day" in result.time_str.lower() or "8am" in result.time_str
        assert result.agent == "news"
        assert "summarize" in result.prompt

    def test_parse_schedule_every_day_without_at(self, parser):
        """Test parsing /schedule 'every day 8:00 am' without 'at' keyword."""
        result = parser.parse("/schedule every day 8:00 am news summarize headlines")
        assert isinstance(result, ScheduleCommand)
        assert result.command_type == CommandType.SCHEDULE
        assert result.time_str == "every day 8:00 am"
        assert result.agent == "news"
        assert "summarize" in result.prompt

    def test_parse_schedule_every_day_no_minutes(self, parser):
        """Test parsing /schedule 'every day 8am' without minutes."""
        result = parser.parse("/schedule every day 8am news daily briefing")
        assert isinstance(result, ScheduleCommand)
        assert result.command_type == CommandType.SCHEDULE
        assert result.time_str == "every day 8am"
        assert result.agent == "news"
        assert "daily briefing" in result.prompt

    # === REMIND command tests ===
    def test_parse_remind_full(self, parser):
        """Test parsing /remind with time and prompt."""
        result = parser.parse("/remind tomorrow at 4am wake up")
        assert isinstance(result, RemindCommand)
        assert result.command_type == CommandType.REMIND
        assert result.time_str == "tomorrow at 4am"
        assert result.prompt == "wake up"

    def test_parse_remind_long_time_expression(self, parser):
        """Test parsing /remind with long time expression."""
        result = parser.parse("/remind in 2 hours and 30 minutes check the oven")
        assert isinstance(result, RemindCommand)
        assert result.command_type == CommandType.REMIND
        # dateparser should recognize "in 2 hours and 30 minutes"
        assert "in" in result.time_str
        assert "check the oven" in result.prompt

    def test_parse_remind_time_only(self, parser):
        """Test parsing /remind with only time."""
        result = parser.parse("/remind in 5 minutes")
        assert isinstance(result, RemindCommand)
        assert result.command_type == CommandType.REMIND
        assert result.time_str == "in 5 minutes"
        assert result.prompt is None

    def test_parse_remind_uppercase(self, parser):
        """Test parsing /REMIND (case insensitive)."""
        result = parser.parse("/REMIND tomorrow test reminder")
        assert isinstance(result, RemindCommand)
        assert result.command_type == CommandType.REMIND

    def test_parse_remind_without_args(self, parser):
        """Test parsing /remind without arguments returns usage message."""
        result = parser.parse("/remind")
        assert isinstance(result, RemindCommand)
        assert "Usage" in result.prompt

    def test_parse_remind_complex_prompt(self, parser):
        """Test parsing /remind with complex F1 example."""
        prompt = "formula1 chinese grand prix sprint race is going to start, what is the latest news today, brief me."
        result = parser.parse(f"/remind tomorrow at 4am {prompt}")
        assert isinstance(result, RemindCommand)
        assert result.command_type == CommandType.REMIND
        assert result.time_str == "tomorrow at 4am"
        assert result.prompt == prompt

    # === NOTE command tests ===
    def test_parse_note_with_content(self, parser):
        """Test parsing /note with content."""
        result = parser.parse("/note remember to call mom")
        assert isinstance(result, NoteCommand)
        assert result.command_type == CommandType.NOTE
        assert result.content == "remember to call mom"

    def test_parse_note_uppercase(self, parser):
        """Test parsing /NOTE (case insensitive)."""
        result = parser.parse("/NOTE important meeting at 3pm")
        assert isinstance(result, NoteCommand)
        assert result.command_type == CommandType.NOTE
        assert result.content == "important meeting at 3pm"

    def test_parse_note_without_content(self, parser):
        """Test parsing /note without content returns default message."""
        result = parser.parse("/note")
        assert isinstance(result, NoteCommand)
        assert result.command_type == CommandType.NOTE
        assert "content" in result.content.lower()

    def test_parse_note_long_content(self, parser):
        """Test parsing /note with long content."""
        content = "This is a very long note that contains multiple sentences. " * 5
        result = parser.parse(f"/note {content}")
        assert isinstance(result, NoteCommand)
        assert result.command_type == CommandType.NOTE
        # Content is stripped, so trailing space is removed
        assert result.content == content.rstrip()

    # === NOTES command tests ===
    def test_parse_notes(self, parser):
        """Test parsing /notes command."""
        result = parser.parse("/notes")
        assert isinstance(result, NotesCommand)
        assert result.command_type == CommandType.NOTES

    def test_parse_notes_uppercase(self, parser):
        """Test parsing /NOTES (case insensitive)."""
        result = parser.parse("/NOTES")
        assert isinstance(result, NotesCommand)
        assert result.command_type == CommandType.NOTES

    # === SCHEDULES command tests ===
    def test_parse_schedules(self, parser):
        """Test parsing /schedules command."""
        result = parser.parse("/schedules")
        assert isinstance(result, SchedulesCommand)
        assert result.command_type == CommandType.SCHEDULES

    def test_parse_schedules_uppercase(self, parser):
        """Test parsing /SCHEDULES (case insensitive)."""
        result = parser.parse("/SCHEDULES")
        assert isinstance(result, SchedulesCommand)
        assert result.command_type == CommandType.SCHEDULES

    def test_parse_schedules_with_args(self, parser):
        """Test /schedules ignores extra arguments."""
        result = parser.parse("/schedules something else")
        assert isinstance(result, SchedulesCommand)
        assert result.command_type == CommandType.SCHEDULES

    # === HELP command tests ===
    def test_parse_help(self, parser):
        """Test parsing /help command."""
        result = parser.parse("/help")
        assert isinstance(result, HelpCommand)
        assert result.command_type == CommandType.HELP

    def test_parse_help_uppercase(self, parser):
        """Test parsing /HELP (case insensitive)."""
        result = parser.parse("/HELP")
        assert isinstance(result, HelpCommand)
        assert result.command_type == CommandType.HELP

    def test_parse_help_with_extra_args(self, parser):
        """Test /help ignores extra arguments."""
        result = parser.parse("/help something else")
        assert isinstance(result, HelpCommand)
        assert result.command_type == CommandType.HELP

    # === DEFAULT mode tests ===
    def test_parse_default_plain_text(self, parser):
        """Test parsing plain text without command prefix."""
        result = parser.parse("hello world")
        assert isinstance(result, QueryCommand)
        assert result.command_type == CommandType.DEFAULT
        assert result.query == "hello world"

    def test_parse_default_question(self, parser):
        """Test parsing a question without command prefix."""
        result = parser.parse("What is the capital of France?")
        assert isinstance(result, QueryCommand)
        assert result.command_type == CommandType.DEFAULT
        assert "capital" in result.query

    def test_parse_default_with_whitespace(self, parser):
        """Test parsing text with leading/trailing whitespace."""
        result = parser.parse("  hello world  ")
        assert isinstance(result, QueryCommand)
        assert result.command_type == CommandType.DEFAULT
        assert result.query == "hello world"

    def test_parse_default_empty_string(self, parser):
        """Test parsing empty string."""
        result = parser.parse("")
        assert isinstance(result, QueryCommand)
        assert result.command_type == CommandType.DEFAULT
        assert result.query == ""

    # === Edge cases ===
    def test_parse_command_with_extra_spaces(self, parser):
        """Test parsing command with extra spaces."""
        result = parser.parse("/learn   python   async")
        assert isinstance(result, QueryCommand)
        assert result.command_type == CommandType.LEARN
        # Extra spaces after the command prefix should be stripped
        assert "python" in result.query

    def test_parse_command_with_newlines_after_command(self, parser):
        """Test parsing command with newlines after command prefix."""
        result = parser.parse("/note this is a multiline note")
        assert isinstance(result, NoteCommand)
        assert result.command_type == CommandType.NOTE

    def test_parse_command_similar_but_not_exact(self, parser):
        """Test text that looks like command but isn't."""
        result = parser.parse("learning about python")
        assert isinstance(result, QueryCommand)
        assert result.command_type == CommandType.DEFAULT
        assert result.query == "learning about python"

    def test_parse_command_as_part_of_sentence(self, parser):
        """Test command prefix as part of a sentence."""
        result = parser.parse("I want to /learn python")
        assert isinstance(result, QueryCommand)
        # Should be treated as default since /learn is not at the start
        assert result.command_type == CommandType.DEFAULT


class TestCommandTypes:
    """Tests for command type enumeration."""

    def test_command_type_values(self):
        """Test that all command types have correct string values."""
        assert CommandType.DEFAULT.value == "default"
        assert CommandType.LEARN.value == "learn"
        assert CommandType.YOUTUBE.value == "youtube"
        assert CommandType.SCHEDULE.value == "schedule"
        assert CommandType.REMIND.value == "remind"
        assert CommandType.NOTE.value == "note"
        assert CommandType.NOTES.value == "notes"
        assert CommandType.HELP.value == "help"

    def test_command_type_count(self):
        """Test that we have the expected number of command types."""
        assert len(CommandType) == 9


class TestCommandDataclasses:
    """Tests for command dataclass structures."""

    def test_query_command_creation(self):
        """Test creating a QueryCommand."""
        cmd = QueryCommand(command_type=CommandType.LEARN, query="test query")
        assert cmd.command_type == CommandType.LEARN
        assert cmd.query == "test query"

    def test_schedule_command_creation(self):
        """Test creating a ScheduleCommand."""
        cmd = ScheduleCommand(
            command_type=CommandType.SCHEDULE,
            time_str="tomorrow",
            agent="developer",
            prompt="review code"
        )
        assert cmd.command_type == CommandType.SCHEDULE
        assert cmd.time_str == "tomorrow"
        assert cmd.agent == "developer"
        assert cmd.prompt == "review code"

    def test_remind_command_creation(self):
        """Test creating a RemindCommand."""
        cmd = RemindCommand(
            command_type=CommandType.REMIND,
            time_str="in 1 hour",
            prompt="meeting"
        )
        assert cmd.command_type == CommandType.REMIND
        assert cmd.time_str == "in 1 hour"
        assert cmd.prompt == "meeting"

    def test_note_command_creation(self):
        """Test creating a NoteCommand."""
        cmd = NoteCommand(command_type=CommandType.NOTE, content="my note")
        assert cmd.command_type == CommandType.NOTE
        assert cmd.content == "my note"

    def test_notes_command_creation(self):
        """Test creating a NotesCommand."""
        cmd = NotesCommand(command_type=CommandType.NOTES)
        assert cmd.command_type == CommandType.NOTES

    def test_help_command_creation(self):
        """Test creating a HelpCommand."""
        cmd = HelpCommand(command_type=CommandType.HELP)
        assert cmd.command_type == CommandType.HELP

    def test_schedule_command_defaults(self):
        """Test ScheduleCommand with optional fields as None."""
        cmd = ScheduleCommand(
            command_type=CommandType.SCHEDULE,
            time_str="tomorrow"
        )
        assert cmd.agent is None
        assert cmd.prompt is None

    def test_remind_command_prompt_default(self):
        """Test RemindCommand with prompt as None."""
        cmd = RemindCommand(
            command_type=CommandType.REMIND,
            time_str="tomorrow"
        )
        assert cmd.prompt is None
