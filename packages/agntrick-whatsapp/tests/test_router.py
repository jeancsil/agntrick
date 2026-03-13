"""Unit tests for WhatsAppRouterAgent command parsing."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Mock agntrick module and all its submodules before importing router
mock_agntrick = MagicMock()

# Mock constants
mock_agntrick.constants = MagicMock()
mock_agntrick.constants.STORAGE_DIR = Path("/tmp/agntrick")

# Mock llm
mock_agntrick.llm = MagicMock()
mock_agntrick.llm.get_default_model = lambda: "gpt-4"

# Mock mcp
mock_agntrick.mcp = MagicMock()
mock_agntrick.mcp.MCPProvider = MagicMock

# Mock registry
mock_agntrick.registry = MagicMock()
mock_agntrick.registry.AgentRegistry = MagicMock

# Mock tools
mock_agntrick.tools = MagicMock()
mock_agntrick.tools.YouTubeTranscriptTool = MagicMock

sys.modules["agntrick"] = mock_agntrick
sys.modules["agntrick.constants"] = mock_agntrick.constants
sys.modules["agntrick.llm"] = mock_agntrick.llm
sys.modules["agntrick.mcp"] = mock_agntrick.mcp
sys.modules["agntrick.registry"] = mock_agntrick.registry
sys.modules["agntrick.tools"] = mock_agntrick.tools

# Mock ChatOpenAI before importing router
mock_chat_openai = MagicMock()
sys.modules["langchain_openai"] = MagicMock()
sys.modules["langchain_openai"].ChatOpenAI = mock_chat_openai

from agntrick_whatsapp.router import WhatsAppRouterAgent


class MockChannel:
    """Mock channel for testing."""
    def __init__(self):
        self.storage_path = Path("/tmp/test_storage")


class TestCommandParsing:
    """Tests for _parse_command method."""

    @pytest.fixture
    def router(self):
        """Create a router instance with mock channel."""
        return WhatsAppRouterAgent(channel=MockChannel())

    def test_parse_remind_basic(self, router):
        """Test basic remind command parsing."""
        result = router._parse_command("/remind tomorrow buy milk")
        assert result is not None
        assert result[0] == "remind"
        assert result[1] == "tomorrow"
        assert result[2] == "buy milk"

    def test_parse_remind_with_time(self, router):
        """Test remind command with specific time."""
        result = router._parse_command("/remind tomorrow at 4am wake up")
        assert result is not None
        assert result[0] == "remind"
        assert result[1] == "tomorrow at 4am"
        assert result[2] == "wake up"

    def test_parse_remind_long_prompt(self, router):
        """Test remind command with long prompt."""
        result = router._parse_command("/remind tomorrow at 4am formula1 chinese grand prix sprint race is going to start")
        assert result is not None
        assert result[0] == "remind"
        assert result[1] == "tomorrow at 4am"
        assert result[2] == "formula1 chinese grand prix sprint race is going to start"

    def test_parse_remind_minimal(self, router):
        """Test remind command with just time."""
        result = router._parse_command("/remind in 5 minutes")
        assert result is not None
        assert result[0] == "remind"
        assert result[1] == "in 5 minutes"
        assert result[2] is None

    def test_parse_remind_in_one_hour(self, router):
        """Test remind command with 'in X time' format."""
        result = router._parse_command("/remind in 2 hours check the oven")
        assert result is not None
        assert result[0] == "remind"
        assert result[1] == "in 2 hours"
        assert result[2] == "check the oven"

    def test_parse_schedule_basic(self, router):
        """Test basic schedule command parsing."""
        result = router._parse_command("/schedule tomorrow agent1 do something")
        assert result is not None
        assert result[0] == "schedule"
        assert result[1] == "tomorrow"
        assert result[2] == "agent1"
        assert result[3] == "do something"

    def test_parse_schedule_no_prompt(self, router):
        """Test schedule command without prompt."""
        result = router._parse_command("/schedule tomorrow agent1")
        assert result is not None
        assert result[0] == "schedule"
        assert result[1] == "tomorrow"
        assert result[2] == "agent1"
        assert result[3] is None

    def test_parse_note(self, router):
        """Test note command parsing."""
        result = router._parse_command("/note remember this")
        assert result is not None
        assert result[0] == "note"
        assert result[1] == "remember this"

    def test_parse_learn(self, router):
        """Test learn command parsing."""
        result = router._parse_command("/learn python programming")
        assert result is not None
        assert result[0] == "learn"
        assert result[1] == "python programming"

    def test_parse_youtube(self, router):
        """Test youtube command parsing."""
        result = router._parse_command("/youtube https://youtube.com/watch?v=123")
        assert result is not None
        assert result[0] == "youtube"
        assert result[1] == "https://youtube.com/watch?v=123"

    def test_parse_default(self, router):
        """Test default mode (no command prefix)."""
        result = router._parse_command("hello world")
        assert result == ("default", "hello world")

    def test_parse_remind_case_insensitive(self, router):
        """Test remind command is case insensitive."""
        result = router._parse_command("/REMIND tomorrow test")
        assert result is not None
        assert result[0] == "remind"

    def test_parse_remind_extra_spaces(self, router):
        """Test remind command with extra spaces."""
        result = router._parse_command("/remind   tomorrow   test")
        assert result is not None
        assert result[0] == "remind"
        assert result[1] == "tomorrow"
        assert result[2] == "test"


class TestStorageInitialization:
    """Tests for storage initialization."""

    def test_storage_attributes_initialized(self):
        """Test that storage attributes are initialized in __init__."""
        router = WhatsAppRouterAgent(channel=MockChannel())
        assert hasattr(router, "_storage_db_path")
        assert hasattr(router, "_task_repo")
        assert hasattr(router, "_note_repo")
        assert router._task_repo is None
        assert router._note_repo is None

    def test_storage_db_path_uses_channel_storage(self):
        """Test that storage db path is based on channel storage_path."""
        router = WhatsAppRouterAgent(channel=MockChannel())
        assert "test_storage" in str(router._storage_db_path)
        assert router._storage_db_path.name == "storage.db"


class TestRemindScheduleRouting:
    """Tests for remind and schedule routing after parsing."""

    @pytest.fixture
    def router(self):
        """Create a router instance with mock channel."""
        return WhatsAppRouterAgent(channel=MockChannel())

    def test_remind_parsing_sets_correct_mode(self, router):
        """Test that remind command sets mode to 'remind' not the time."""
        result = router._parse_command("/remind tomorrow do something")
        assert result[0] == "remind", "Mode should be 'remind', not 'tomorrow'"

    def test_schedule_parsing_sets_correct_mode(self, router):
        """Test that schedule command sets mode to 'schedule' not the time."""
        result = router._parse_command("/schedule tomorrow agent1 do something")
        assert result[0] == "schedule", "Mode should be 'schedule', not 'tomorrow'"

    def test_remind_time_is_fully_extracted(self, router):
        """Test that full time expression is extracted for remind."""
        result = router._parse_command("/remind in 5 minutes test")
        assert result[1] == "in 5 minutes", "Time string should include full time expression"
        assert result[2] == "test"
