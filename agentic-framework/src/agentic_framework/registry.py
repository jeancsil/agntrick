import importlib
import logging
import pkgutil
from typing import Callable, Dict, List, Optional, Type

from agentic_framework.interfaces.base import Agent

# Package to scan for agent modules; imported lazily in discover_agents() to avoid circular
# import (agent modules do "from agentic_framework.registry import AgentRegistry").
# Must be a package whose __init__.py does NOT import concrete agent modules.
_AGENTS_PACKAGE_NAME = "agentic_framework.core"
_logger = logging.getLogger(__name__)


class DuplicateAgentRegistrationError(Exception):
    """Raised when attempting to register an agent with a name that's already in use."""

    def __init__(self, name: str, existing: Type[Agent], new: Type[Agent]):
        self.name = name
        self.existing = existing
        self.new = new
        super().__init__(
            f"Agent '{name}' is already registered with class {existing.__name__}. "
            f"Attempted to register with {new.__name__}."
        )


class AgentRegistry:
    _registry: Dict[str, Type[Agent]] = {}
    _mcp_servers: Dict[str, Optional[List[str]]] = {}
    _strict_registration: bool = False  # If True, duplicates raise an error

    @classmethod
    def set_strict_registration(cls, strict: bool = True) -> None:
        """Set whether duplicate registrations should raise an error.

        When strict=True, attempting to register an agent with an existing name
        will raise DuplicateAgentRegistrationError. When strict=False (default),
        a warning is logged and the existing registration is overwritten.
        """
        cls._strict_registration = strict

    @classmethod
    def register(
        cls,
        name: str,
        mcp_servers: Optional[List[str]] = None,
        *,
        override: bool = False,
    ) -> Callable[[Type[Agent]], Type[Agent]]:
        """Decorator to register an agent class and its allowed MCP servers.

        Args:
            name: The agent name to register.
            mcp_servers: list of keys from mcp.config.DEFAULT_MCP_SERVERS this agent may use.
                        None or [] means the agent has no MCP access.
            override: If True, allow overwriting an existing registration even in strict mode.

        Raises:
            DuplicateAgentRegistrationError: If strict_registration is True and the name
                                          is already registered (unless override=True).
        """

        def decorator(agent_cls: Type[Agent]) -> Type[Agent]:
            if name in cls._registry and not override:
                existing_cls = cls._registry[name]
                if cls._strict_registration:
                    raise DuplicateAgentRegistrationError(name, existing_cls, agent_cls)
                _logger.warning(
                    "Duplicate agent registration: '%s' already registered with %s, overwriting with %s",
                    name,
                    existing_cls.__name__,
                    agent_cls.__name__,
                )
            cls._registry[name] = agent_cls
            cls._mcp_servers[name] = mcp_servers
            _logger.debug("Registered agent '%s' with class %s", name, agent_cls.__name__)
            return agent_cls

        return decorator

    @classmethod
    def get(cls, name: str) -> Optional[Type[Agent]]:
        """Get an agent class by name."""
        return cls._registry.get(name)

    @classmethod
    def get_mcp_servers(cls, name: str) -> Optional[List[str]]:
        """Return the list of MCP server names this agent is allowed to use, or None if no access."""
        return cls._mcp_servers.get(name)

    @classmethod
    def list_agents(cls) -> list[str]:
        """List all registered agent names."""
        return list(cls._registry.keys())

    @classmethod
    def discover_agents(cls) -> None:
        """Import all modules in the agents package so @AgentRegistry.register() decorators run."""
        agents_pkg = importlib.import_module(_AGENTS_PACKAGE_NAME)
        prefix = agents_pkg.__name__ + "."
        for modinfo in pkgutil.iter_modules(agents_pkg.__path__, prefix):
            importlib.import_module(modinfo.name)
