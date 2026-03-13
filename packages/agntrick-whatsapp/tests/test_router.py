"""Unit tests for WhatsAppRouterAgent."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

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


class TestCommandParserIntegration:
    """Tests for command parser integration with router."""

    def test_router_has_command_parser(self):
        """Test that router has a command parser instance."""
        router = WhatsAppRouterAgent(channel=MockChannel())
        assert hasattr(router, "_command_parser")

    def test_command_parser_is_used(self):
        """Test that the command parser is properly initialized."""
        router = WhatsAppRouterAgent(channel=MockChannel())
        assert router._command_parser is not None
