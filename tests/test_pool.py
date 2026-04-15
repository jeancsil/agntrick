"""Tests for TenantAgentPool."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestTenantAgentPool:
    """Tests for agent pooling per tenant."""

    def test_pool_starts_empty(self) -> None:
        from agntrick.api.pool import TenantAgentPool

        pool = TenantAgentPool()
        assert len(pool) == 0

    @pytest.mark.asyncio
    async def test_creates_agent_on_first_request(self) -> None:
        from agntrick.api.pool import TenantAgentPool

        pool = TenantAgentPool(max_size=5)
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value="Hello")

        with patch.object(pool, "_create", return_value=mock_agent) as mock_create:
            agent = await pool.get_or_create(
                tenant_id="primary",
                agent_name="assistant",
                agent_cls=MagicMock(),
                agent_kwargs={},
            )
            assert agent is mock_agent
            assert mock_create.call_count == 1
            assert len(pool) == 1

    @pytest.mark.asyncio
    async def test_reuses_agent_on_second_request(self) -> None:
        from agntrick.api.pool import TenantAgentPool

        pool = TenantAgentPool(max_size=5)
        mock_agent = MagicMock()

        with patch.object(pool, "_create", return_value=mock_agent):
            agent1 = await pool.get_or_create(
                tenant_id="primary",
                agent_name="assistant",
                agent_cls=MagicMock(),
                agent_kwargs={},
            )
            agent2 = await pool.get_or_create(
                tenant_id="primary",
                agent_name="assistant",
                agent_cls=MagicMock(),
                agent_kwargs={},
            )
            assert agent1 is agent2
            assert len(pool) == 1

    @pytest.mark.asyncio
    async def test_separate_tenants_get_separate_agents(self) -> None:
        from agntrick.api.pool import TenantAgentPool

        pool = TenantAgentPool(max_size=5)

        with patch.object(pool, "_create", side_effect=[MagicMock(), MagicMock()]):
            agent1 = await pool.get_or_create(
                tenant_id="tenant-a",
                agent_name="assistant",
                agent_cls=MagicMock(),
                agent_kwargs={},
            )
            agent2 = await pool.get_or_create(
                tenant_id="tenant-b",
                agent_name="assistant",
                agent_cls=MagicMock(),
                agent_kwargs={},
            )
            assert agent1 is not agent2
            assert len(pool) == 2

    @pytest.mark.asyncio
    async def test_evict_removes_oldest_entry(self) -> None:
        from agntrick.api.pool import TenantAgentPool

        pool = TenantAgentPool(max_size=2)
        pool._agents = {
            "tenant-a:assistant": MagicMock(),
            "tenant-b:assistant": MagicMock(),
        }
        pool._access_order = ["tenant-a:assistant", "tenant-b:assistant"]

        await pool._evict_if_needed()

        assert "tenant-a:assistant" not in pool._agents
        assert "tenant-b:assistant" in pool._agents
        assert len(pool) == 1

    @pytest.mark.asyncio
    async def test_evict_calls_cleanup(self) -> None:
        from agntrick.api.pool import TenantAgentPool

        pool = TenantAgentPool(max_size=1)
        mock_old = MagicMock()
        mock_old.cleanup = AsyncMock()
        pool._agents = {"old:assistant": mock_old}
        pool._access_order = ["old:assistant"]

        await pool._evict_if_needed()

        mock_old.cleanup.assert_called_once()
