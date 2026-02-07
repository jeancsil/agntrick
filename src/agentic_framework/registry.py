from typing import Dict, Optional, Type

from agentic_framework.interfaces.base import Agent


class AgentRegistry:
    _registry: Dict[str, Type[Agent]] = {}

    @classmethod
    def register(cls, name: str):
        """Decorator to register an agent class."""

        def decorator(agent_cls: Type[Agent]):
            cls._registry[name] = agent_cls
            return agent_cls

        return decorator

    @classmethod
    def get(cls, name: str) -> Optional[Type[Agent]]:
        """Get an agent class by name."""
        return cls._registry.get(name)

    @classmethod
    def list_agents(cls) -> list[str]:
        """List all registered agent names."""
        return list(cls._registry.keys())
