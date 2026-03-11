"""Pydantic models for WhatsApp channel configuration validation.

This module provides type-safe configuration validation for WhatsApp agent,
ensuring all required fields are present and properly typed.
"""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


def parse_mcp_servers_str(value: str) -> list[str]:
    """Parse a comma-separated MCP server string into a list.

    Accepts:
        - ``none`` / `````` / ``disabled`` → empty list (MCP disabled)
        - ``"fetch,web-forager"`` → ``["fetch", "web-forager"]``

    Args:
        value: The raw string value from CLI or config file.

    Returns:
        List of server names, possibly empty.
    """
    if value.lower() in ("none", "", "disabled"):
        return []
    return [s.strip() for s in value.split(",") if s.strip()]


class PrivacyConfig(BaseModel):
    """Privacy and filtering configuration."""

    allowed_contact: str = Field(
        ...,
        description="Phone number to allow messages from (e.g., '+34 666 666 666').",
    )
    log_filtered_messages: bool = Field(
        default=False,
        description="Log filtered messages for debugging.",
    )


class FeatureFlags(BaseModel):
    """Feature toggles for WhatsApp agent."""

    text_messages: bool = Field(default=True, description="Enable text messages.")
    media_messages: bool = Field(default=True, description="Enable media (images, videos, documents, audio).")
    group_messages: bool = Field(
        default=False,
        description=(
            "Enable group messages (disabled by default for privacy). "
            "Group messages are always filtered at the channel level."
        ),
    )
    presence_updates: bool = Field(default=True, description="Enable presence (online/typing status).")
    typing_indicators: bool = Field(default=True, description="Send typing indicators when processing.")


class ChannelConfig(BaseModel):
    """WhatsApp channel configuration."""

    type: str = Field(default="whatsapp", description="Channel type.")
    storage_path: str = Field(
        default="~/storage/whatsapp",
        description="Directory for WhatsApp data storage.",
    )


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = Field(default="INFO", description="Log level (DEBUG, INFO, WARNING, ERROR).")
    file: str = Field(default="logs/agent.log", description="Log file location.")


class AudioTranscriberConfig(BaseModel):
    """Audio transcriber configuration for Groq API."""

    model: str = Field(
        default="whisper-large-v3-turbo",
        description="Groq Whisper model name (default: whisper-large-v3-turbo).",
    )
    timeout: float = Field(
        default=60.0,
        ge=1.0,
        description="Request timeout in seconds.",
    )
    config_file: str | None = Field(
        default=None,
        description="Path to audio transcriber config file (optional).",
    )

    @field_validator("model", mode="before")
    @classmethod
    def validate_model(cls, v: str) -> str:
        """Validate model name is a supported Groq Whisper model."""
        available_models = {"whisper-large-v3", "whisper-large-v3-turbo"}
        if v not in available_models:
            raise ValueError(f"Model must be one of: {', '.join(available_models)}. Got: {v}")
        return v


class WhatsAppBridgeConfig(BaseModel):
    """WhatsApp bridge specific configuration."""

    auto_setup: bool = Field(default=True, description="Auto-clone Go bridge on first run.")
    auto_connect: bool = Field(default=True, description="Auto-connect on startup.")
    bridge_timeout_sec: int = Field(default=180, ge=1, le=600, description="Max wait for bridge startup (seconds).")
    poll_interval_sec: float = Field(
        default=1.0, ge=0.1, le=60.0, description="Check for new messages interval (seconds)."
    )


class WhatsAppAgentConfig(BaseModel):
    """Complete WhatsApp agent configuration.

    This model validates the entire configuration structure,
    ensuring all required fields are present and properly typed.

    Example:
        >>> import yaml
        >>> with open("whatsapp.yaml") as f:
        ...     config_dict = yaml.safe_load(f)
        >>> config = WhatsAppAgentConfig.model_validate(config_dict)
        >>> config.privacy.allowed_contact
        '+34 666 666 666'
        >>> config.audio_transcriber.model
        'whisper-large-v3-turbo'
    """

    model: str | None = Field(default=None, description="LLM model name.")
    mcp_servers: list[str] | None = Field(default=None, description="MCP servers to use.")
    channel: ChannelConfig = Field(default_factory=ChannelConfig, description="Channel configuration.")
    privacy: PrivacyConfig = Field(..., description="Privacy configuration.")
    features: FeatureFlags = Field(default_factory=FeatureFlags, description="Feature flags.")
    audio_transcriber: AudioTranscriberConfig = Field(
        default_factory=AudioTranscriberConfig,
        description="Audio transcriber configuration for Groq API.",
    )
    whatsapp_bridge: WhatsAppBridgeConfig = Field(
        default_factory=WhatsAppBridgeConfig,
        description="Bridge configuration.",
    )
    logging: LoggingConfig = Field(default_factory=LoggingConfig, description="Logging configuration.")

    @field_validator("mcp_servers", mode="before")
    @classmethod
    def parse_mcp_servers(cls, v: Any) -> list[str] | None:
        """Parse MCP servers from string or list format."""
        if v is None:
            return None
        if isinstance(v, str):
            return parse_mcp_servers_str(v)
        if isinstance(v, list):
            return v
        raise ValueError(f"mcp_servers must be a list or string, got {type(v).__name__}")

    @field_validator("channel", mode="before")
    @classmethod
    def expand_home_path(cls, v: Any) -> ChannelConfig:
        """Expand ~ to user's home directory in storage_path."""
        if isinstance(v, dict):
            storage_path = v.get("storage_path", "~/storage/whatsapp")
            if storage_path.startswith("~"):
                storage_path = str(Path(storage_path).expanduser())
                v["storage_path"] = storage_path
                v = ChannelConfig(**v)
        return v

    def get_storage_path(self) -> Path:
        """Get the storage path as a Path object, expanded from ~ if needed."""
        return Path(self.channel.storage_path).expanduser()
