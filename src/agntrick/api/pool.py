"""Tenant-scoped agent pool for reusing agent instances across requests."""

import asyncio
import logging
from typing import Any

from agntrick.agent import AgentBase

logger = logging.getLogger(__name__)


class TenantAgentPool:
    """Pool of agent instances keyed by tenant_id:agent_name.

    Agents are created on first access and reused across requests.
    LRU eviction when pool exceeds max_size.
    """

    def __init__(self, max_size: int = 10) -> None:
        self._agents: dict[str, AgentBase] = {}
        self._access_order: list[str] = []
        self._lock = asyncio.Lock()
        self.max_size = max_size

    def __len__(self) -> int:
        return len(self._agents)

    async def get_or_create(
        self,
        tenant_id: str,
        agent_name: str,
        agent_cls: type,
        agent_kwargs: dict[str, Any],
    ) -> AgentBase:
        """Get a pooled agent or create one if not cached.

        Args:
            tenant_id: Tenant identifier.
            agent_name: Agent name (e.g., "assistant").
            agent_cls: Agent class to instantiate.
            agent_kwargs: Keyword arguments for agent constructor.

        Returns:
            Agent instance (pooled or freshly created).
        """
        key = f"{tenant_id}:{agent_name}"

        if key in self._agents:
            self._touch(key)
            logger.debug(f"[pool] reuse agent: {key}")
            return self._agents[key]

        async with self._lock:
            # Double-checked locking
            if key in self._agents:
                self._touch(key)
                return self._agents[key]

            await self._evict_if_needed()
            agent = await self._create(agent_cls, agent_kwargs)
            self._agents[key] = agent
            self._access_order.append(key)
            logger.info(f"[pool] created agent: {key} (pool_size={len(self._agents)})")
            return agent

    async def _create(
        self,
        agent_cls: type,
        agent_kwargs: dict[str, Any],
    ) -> AgentBase:
        """Create and initialize a new agent instance.

        Args:
            agent_cls: Agent class to instantiate.
            agent_kwargs: Constructor arguments.

        Returns:
            Initialized agent with MCP tools loaded.
        """
        agent: AgentBase = agent_cls(**agent_kwargs)
        # Trigger lazy initialization (MCP connection, graph compilation)
        await agent._ensure_initialized()
        return agent

    def _touch(self, key: str) -> None:
        """Move key to end of access order (most recently used)."""
        if key in self._access_order:
            self._access_order.remove(key)
            self._access_order.append(key)

    async def _evict_if_needed(self) -> None:
        """Evict oldest entry if pool is at capacity."""
        while len(self._agents) >= self.max_size and self._access_order:
            oldest_key = self._access_order.pop(0)
            agent = self._agents.pop(oldest_key, None)
            if agent:
                await self._safe_cleanup(agent, oldest_key)
            logger.info(f"[pool] evicted agent: {oldest_key}")

    @staticmethod
    async def _safe_cleanup(agent: AgentBase, key: str) -> None:
        """Safely clean up an evicted agent."""
        try:
            if hasattr(agent, "cleanup"):
                await agent.cleanup()  # type: ignore[attr-defined]
        except Exception as e:
            logger.warning(f"[pool] cleanup failed for {key}: {e}")

    async def evict(self, tenant_id: str, agent_name: str) -> None:
        """Manually evict an agent (e.g., after MCP connection failure).

        Args:
            tenant_id: Tenant identifier.
            agent_name: Agent name.
        """
        key = f"{tenant_id}:{agent_name}"
        agent = self._agents.pop(key, None)
        if key in self._access_order:
            self._access_order.remove(key)
        if agent:
            await self._safe_cleanup(agent, key)
        logger.info(f"[pool] manually evicted: {key}")
