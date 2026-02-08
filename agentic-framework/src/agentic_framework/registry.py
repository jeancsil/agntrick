import importlib
import pkgutil
from typing import Dict, List, Optional, Type

from agentic_framework.interfaces.base import Agent

# Package to scan for agent modules; imported lazily in discover_agents() to avoid circular
# import (agent modules do "from agentic_framework.registry import AgentRegistry").
# Must be a package whose __init__.py does NOT import agent modules (core/__init__.py is empty).
_AGENTS_PACKAGE_NAME = "agentic_framework.core"


class AgentRegistry:
    _registry: Dict[str, Type[Agent]] = {}
    _mcp_servers: Dict[str, Optional[List[str]]] = {}

    @classmethod
    def register(cls, name: str, mcp_servers: Optional[List[str]] = None):
        """Decorator to register an agent class and its allowed MCP servers.

        mcp_servers: list of keys from mcp.config.DEFAULT_MCP_SERVERS this agent may use.
                     None or [] means the agent has no MCP access.
        """

        def decorator(agent_cls: Type[Agent]):
            cls._registry[name] = agent_cls
            cls._mcp_servers[name] = mcp_servers
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
