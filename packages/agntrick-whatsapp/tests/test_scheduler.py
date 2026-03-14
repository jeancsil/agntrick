"""Unit tests for time parsing and scheduling module."""
import sys
from datetime import UTC, datetime, timedelta
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

from agntrick_whatsapp.storage.scheduler import (
    calculate_next_run,
    parse_natural_time,
    _pattern_to_cron,
)


class TestParseNaturalTime:
    """Tests for parse_natural_time function."""

    def test_parse_every_day_with_at(self):
        """Test parsing 'every day at 8am'."""
        next_run, cron = parse_natural_time("every day at 8am")
        assert cron == "0 8 * * *"
        assert next_run.hour == 8
        assert next_run.minute == 0

    def test_parse_every_day_without_at(self):
        """Test parsing 'every day 8:00 am' without 'at' keyword."""
        next_run, cron = parse_natural_time("every day 8:00 am")
        assert cron == "0 8 * * *"
        assert next_run.hour == 8
        assert next_run.minute == 0

    def test_parse_every_day_with_minutes_and_pm(self):
        """Test parsing 'every day 4:30 pm'."""
        next_run, cron = parse_natural_time("every day 4:30 pm")
        assert cron == "30 16 * * *"
        assert next_run.hour == 16
        assert next_run.minute == 30

    def test_parse_every_day_8am_no_minutes(self):
        """Test parsing 'every day 8am' with no minutes."""
        next_run, cron = parse_natural_time("every day 8am")
        assert cron == "0 8 * * *"
        assert next_run.hour == 8
        assert next_run.minute == 0

    def test_parse_tomorrow_at_noon(self):
        """Test parsing 'tomorrow at noon' (one-time, no cron)."""
        tomorrow = datetime.now(UTC) + timedelta(days=1)
        next_run, cron = parse_natural_time("tomorrow at noon")
        assert cron is None  # One-time task
        assert next_run.hour == 12

    def test_parse_in_2_hours(self):
        """Test parsing 'in 2 hours'."""
        now = datetime.now(UTC)
        next_run, cron = parse_natural_time("in 2 hours")
        assert cron is None
        # next_run is timezone-naive from dateparser, make now naive for comparison
        now_naive = now.replace(tzinfo=None)
        assert (next_run - now_naive).total_seconds() >= 7000  # ~2 hours

    def test_invalid_time_expression_raises_error(self):
        """Test that invalid time expressions raise ValueError."""
        with pytest.raises(ValueError, match="Could not parse time expression"):
            parse_natural_time("invalid time string")


class TestPatternToCron:
    """Tests for _pattern_to_cron function."""

    def test_every_day_at_8am(self):
        """Test converting 'every day at 8am' pattern to cron."""
        match = MagicMock()
        match.group.side_effect = ["8", "0", "am"]
        cron = _pattern_to_cron(match, "every_day_at")
        assert cron == "0 8 * * *"

    def test_every_day_at_5pm(self):
        """Test converting 'every day at 5pm' pattern to cron."""
        match = MagicMock()
        match.group.side_effect = ["5", "0", "pm"]
        cron = _pattern_to_cron(match, "every_day_at")
        assert cron == "0 17 * * *"

    def test_every_day_at_12pm_noon(self):
        """Test that 12pm is correctly converted (noon = 12, not 0)."""
        match = MagicMock()
        match.group.side_effect = ["12", "0", "pm"]
        cron = _pattern_to_cron(match, "every_day_at")
        assert cron == "0 12 * * *"

    def test_every_day_at_12am_midnight(self):
        """Test that 12am is correctly converted (midnight = 0)."""
        match = MagicMock()
        match.group.side_effect = ["12", "0", "am"]
        cron = _pattern_to_cron(match, "every_day_at")
        assert cron == "0 0 * * *"

    def test_every_day_930am_with_minutes(self):
        """Test converting 'every day 9:30 am' to cron."""
        match = MagicMock()
        match.group.side_effect = ["9", "30", "am"]
        cron = _pattern_to_cron(match, "every_day_at")
        assert cron == "30 9 * * *"

    def test_every_day_without_ampm_defaults_to_am(self):
        """Test that missing am/pm defaults to am."""
        match = MagicMock()
        match.group.side_effect = ["8", "0", None]
        cron = _pattern_to_cron(match, "every_day_at")
        assert cron == "0 8 * * *"


class TestCalculateNextRun:
    """Tests for calculate_next_run function."""

    def test_daily_cron_calculates_next_run(self):
        """Test that daily cron calculates next day's run."""
        cron = "0 8 * * *"  # Daily at 8am
        next_run = calculate_next_run(cron)
        assert next_run.hour == 8
        assert next_run.minute == 0

    def test_cron_with_minutes(self):
        """Test cron expression with specific minute."""
        cron = "30 14 * * *"  # Daily at 2:30pm
        next_run = calculate_next_run(cron)
        assert next_run.hour == 14
        assert next_run.minute == 30

    def test_invalid_cron_raises_error(self):
        """Test that invalid cron raises ValueError."""
        with pytest.raises(ValueError, match="Invalid cron expression"):
            calculate_next_run("invalid cron")
