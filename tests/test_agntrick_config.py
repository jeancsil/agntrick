"""Tests for agntrick package - config module."""

import os
import tempfile

from agntrick.config import (
    AgentsConfig,
    AgntrickConfig,
    LLMConfig,
    LoggingConfig,
    MCPConfig,
    get_config,
    reset_config,
)


def test_agntrick_config_defaults():
    """Test default configuration values."""
    config = AgntrickConfig()

    assert config.llm.provider is None
    assert config.llm.model is None
    assert config.llm.temperature == 0.1  # Default is 0.1 not 0.7

    assert config.logging.level == "INFO"

    assert config.mcp.servers == {}  # Default is empty dict

    assert config.agents.prompts_dir is None


def test_agntrick_config_from_dict():
    """Test creating config from dictionary."""
    data = {
        "llm": {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "temperature": 0.5,
        },
        "logging": {
            "level": "DEBUG",
        },
        "mcp": {
            "servers": {"fetch": {}},
        },
    }

    config = AgntrickConfig.from_dict(data)

    assert config.llm.provider == "anthropic"
    assert config.llm.model == "claude-sonnet-4-6"
    assert config.llm.temperature == 0.5
    assert config.logging.level == "DEBUG"
    assert "fetch" in config.mcp.servers


def test_agntrick_config_load_from_file():
    """Test loading config from YAML file."""
    yaml_content = """
llm:
  provider: openai
  model: gpt-4o
  temperature: 0.8

logging:
  level: WARNING

mcp:
  servers:
    fetch:
      url: https://example.com
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()

        try:
            # Set environment to use this config file
            old_env = os.environ.get("AGNTRICK_CONFIG")
            os.environ["AGNTRICK_CONFIG"] = f.name
            reset_config()

            config = get_config(force_reload=True)
            assert config.llm.provider == "openai"
            assert config.llm.model == "gpt-4o"
            assert config.llm.temperature == 0.8
            assert config.logging.level == "WARNING"

            # Restore
            if old_env:
                os.environ["AGNTRICK_CONFIG"] = old_env
            else:
                os.environ.pop("AGNTRICK_CONFIG", None)
            reset_config()
        finally:
            os.unlink(f.name)


def test_agntrick_config_global_instance():
    """Test global config instance management."""
    reset_config()

    # Get should return a config
    config = get_config()
    assert config is not None
    assert isinstance(config, AgntrickConfig)

    # Reset and get again
    reset_config()
    config2 = get_config()
    assert config2 is not None


def test_agntrick_llm_config():
    """Test LLMConfig dataclass."""
    config = LLMConfig(
        provider="anthropic",
        model="claude-sonnet-4-6",
        temperature=0.9,
        max_tokens=4096,
    )

    assert config.provider == "anthropic"
    assert config.model == "claude-sonnet-4-6"
    assert config.temperature == 0.9
    assert config.max_tokens == 4096


def test_agntrick_logging_config():
    """Test LoggingConfig dataclass."""
    config = LoggingConfig(
        level="DEBUG",
        directory="/tmp/logs",
        file="test.log",
    )

    assert config.level == "DEBUG"
    assert config.directory == "/tmp/logs"
    assert config.file == "test.log"


def test_agntrick_mcp_config():
    """Test MCPConfig dataclass."""
    config = MCPConfig(servers={"fetch": {"url": "https://example.com"}})

    assert "fetch" in config.servers


def test_agntrick_agents_config():
    """Test AgentsConfig dataclass."""
    config = AgentsConfig(
        prompts_dir="./prompts",
    )

    assert config.prompts_dir == "./prompts"


def test_mcp_config_has_default_timeout():
    """MCPConfig should have timeout field with default 60."""
    config = MCPConfig()
    assert config.timeout == 60


def test_mcp_config_custom_timeout():
    """MCPConfig should accept custom timeout."""
    config = MCPConfig(timeout=120)
    assert config.timeout == 120
