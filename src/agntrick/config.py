"""YAML-based configuration management for agntrick.

This module provides configuration loading from YAML files with environment
variable fallback. Configuration files are searched in order:
1. ./.agntrick.yaml (current directory)
2. ~/.agntrick.yaml (home directory)
3. AGNTRICK_CONFIG environment variable
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class LLMConfig:
    """LLM provider configuration."""

    provider: str | None = None
    model: str | None = None
    temperature: float = 0.1
    max_tokens: int | None = None


@dataclass
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"
    file: str | None = None
    directory: str | None = None


@dataclass
class MCPConfig:
    """MCP server configuration."""

    servers: dict[str, dict[str, Any]] = field(default_factory=dict)
    timeout: int = 60  # Connection timeout in seconds
    toolbox_url: str | None = None  # Toolbox MCP server URL


@dataclass
class AgentsConfig:
    """Agent-specific configuration."""

    prompts_dir: str | None = None
    default_agent_name: str = "Assistant"  # Default agent name for prompts
    system_prompt_template: str | None = None  # Optional custom system prompt template
    system_prompt_file: str | None = None  # Path to file containing system prompt template


@dataclass
class APIConfig:
    """API server configuration."""

    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False


@dataclass
class AuthConfig:
    """Authentication configuration."""

    api_keys: dict[str, str] = field(default_factory=dict)


@dataclass
class StorageConfig:
    """Storage configuration."""

    base_path: str | None = None

    def get_tenant_db_path(self, tenant_id: str) -> Path:
        safe_id = "".join(c for c in tenant_id if c.isalnum() or c in "-_")
        base = Path(self.base_path) if self.base_path else Path.home() / ".local" / "share" / "agntrick"
        return base / "tenants" / safe_id / "agntrick.db"


@dataclass
class WhatsAppTenantConfig:
    """Per-tenant WhatsApp configuration."""

    id: str = ""
    phone: str = ""
    default_agent: str = "developer"
    allowed_contacts: list[str] = field(default_factory=list)
    system_prompt: str | None = None


@dataclass
class WhatsAppConfig:
    """WhatsApp channel configuration."""

    tenants: list[WhatsAppTenantConfig] = field(default_factory=list)

    def get_tenant_by_phone(self, phone: str) -> WhatsAppTenantConfig | None:
        for t in self.tenants:
            if t.phone == phone:
                return t
        return None


@dataclass
class AgntrickConfig:
    """Main configuration class for agntrick.

    This class holds all configuration settings with sensible defaults.
    Configuration can be loaded from YAML files and overridden by environment
    variables.
    """

    llm: LLMConfig = field(default_factory=LLMConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    agents: AgentsConfig = field(default_factory=AgentsConfig)
    api: APIConfig = field(default_factory=APIConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    whatsapp: WhatsAppConfig = field(default_factory=WhatsAppConfig)

    _config_path: str | None = field(default=None, init=False, repr=False)

    @classmethod
    def from_dict(cls, config_dict: dict[str, Any]) -> "AgntrickConfig":
        """Create configuration from a dictionary.

        Args:
            config_dict: Dictionary containing configuration values.

        Returns:
            A new AgntrickConfig instance.
        """
        # Parse WhatsApp tenants
        wa_dict = config_dict.get("whatsapp", {})
        tenants = []
        for t in wa_dict.get("tenants", []):
            tenants.append(
                WhatsAppTenantConfig(
                    id=t.get("id", ""),
                    phone=t.get("phone", ""),
                    default_agent=t.get("default_agent", "developer"),
                    allowed_contacts=t.get("allowed_contacts", []),
                    system_prompt=t.get("system_prompt"),
                )
            )

        return cls(
            llm=LLMConfig(**config_dict.get("llm", {})),
            logging=LoggingConfig(**config_dict.get("logging", {})),
            mcp=MCPConfig(**config_dict.get("mcp", {})),
            agents=AgentsConfig(**config_dict.get("agents", {})),
            api=APIConfig(**config_dict.get("api", {})),
            auth=AuthConfig(
                api_keys=config_dict.get("auth", {}).get("api_keys", {}),
            ),
            storage=StorageConfig(**config_dict.get("storage", {})),
            whatsapp=WhatsAppConfig(tenants=tenants),
        )


# Global config instance
_config: AgntrickConfig | None = None


def _find_config_file() -> Path | None:
    """Find the agntrick configuration file.

    Searches in order (highest to lowest priority):
    1. AGNTRICK_CONFIG environment variable
    2. ./.agntrick.yaml (current directory)
    3. ~/.agntrick.yaml (home directory)

    Returns:
        Path to the configuration file, or None if not found.
    """
    # Check environment variable first (highest priority)
    env_config = os.getenv("AGNTRICK_CONFIG")
    if env_config:
        env_path = Path(env_config)
        if env_path.exists():
            return env_path
        # Env var explicitly set but file missing — don't fall through
        return None

    # Check current directory
    local_config = Path.cwd() / ".agntrick.yaml"
    if local_config.exists():
        return local_config

    # Check home directory
    home_config = Path.home() / ".agntrick.yaml"
    if home_config.exists():
        return home_config

    return None


def get_config(force_reload: bool = False) -> AgntrickConfig:
    """Get the current configuration.

    Loads configuration from YAML files on first call. Subsequent calls
    return the cached configuration unless force_reload is True.

    Args:
        force_reload: If True, reload configuration from file even if cached.

    Returns:
        The current AgntrickConfig instance.
    """
    global _config

    if _config is not None and not force_reload:
        return _config

    config_file = _find_config_file()

    if config_file is None:
        # No config file found, use defaults
        _config = AgntrickConfig()
        return _config

    try:
        with config_file.open() as f:
            config_dict = yaml.safe_load(f) or {}

        _config = AgntrickConfig.from_dict(config_dict)
        _config._config_path = str(config_file)
        return _config

    except Exception as e:
        from agntrick.exceptions import ConfigurationError

        raise ConfigurationError(f"Failed to load configuration: {e}", str(config_file))


def reset_config() -> None:
    """Reset the cached configuration.

    This forces the next call to get_config() to reload from file.
    """
    global _config
    _config = None
