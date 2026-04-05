"""Tests for chat_cli module."""

import subprocess
from unittest.mock import MagicMock, Mock, patch

import pytest

from agntrick.config import AgntrickConfig, WhatsAppTenantConfig


class TestMCPServerManager:
    """Tests for MCPServerManager class."""

    def test_start_starts_subprocess_when_toolkit_path_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """start() should start subprocess when AGNTRICK_TOOLKIT_PATH is set and exists."""
        from agntrick.chat_cli import MCPServerManager

        # Set up environment
        toolkit_path = "/path/to/toolkit"
        monkeypatch.setenv("AGNTRICK_TOOLKIT_PATH", toolkit_path)

        # Mock Path.exists to return True
        with patch("agntrick.chat_cli.Path") as mock_path_class:
            mock_path = Mock()
            mock_path.exists.return_value = True
            mock_path_class.return_value = mock_path

            # Mock subprocess.Popen
            mock_process = MagicMock()
            mock_process.pid = 12345

            with patch("subprocess.Popen", return_value=mock_process) as mock_popen:
                # Mock atexit.register to avoid side effects
                with patch("atexit.register") as mock_atexit:
                    manager = MCPServerManager()
                    manager.start()

                    # Verify Popen was called with correct arguments
                    mock_popen.assert_called_once()
                    call_args = mock_popen.call_args
                    assert call_args[0][0] == ["uv", "run", "python", "-m", "agentic_toolkit"]
                    assert call_args[1]["start_new_session"] is True

                    # Verify process is set
                    assert manager.process is mock_process

                    # Verify atexit was registered
                    mock_atexit.assert_called_once_with(manager.stop)

    def test_start_skips_when_toolkit_path_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """start() should skip when AGNTRICK_TOOLKIT_PATH is not set."""
        from agntrick.chat_cli import MCPServerManager

        # Ensure env var is not set
        monkeypatch.delenv("AGNTRICK_TOOLKIT_PATH", raising=False)

        manager = MCPServerManager()
        manager.start()

        # Process should be None
        assert manager.process is None

    def test_start_skips_when_toolkit_path_does_not_exist(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """start() should skip when AGNTRICK_TOOLKIT_PATH doesn't exist."""
        from agntrick.chat_cli import MCPServerManager

        # Set up environment
        toolkit_path = "/nonexistent/path"
        monkeypatch.setenv("AGNTRICK_TOOLKIT_PATH", toolkit_path)

        # Mock Path.exists to return False
        with patch("agntrick.chat_cli.Path") as mock_path_class:
            mock_path = Mock()
            mock_path.exists.return_value = False
            mock_path_class.return_value = mock_path

            manager = MCPServerManager()

            with patch("agntrick.chat_cli.logger") as mock_logger:
                manager.start()

                # Process should be None
                assert manager.process is None

                # Warning should be logged
                mock_logger.warning.assert_called_once()

    def test_stop_kills_running_process(self) -> None:
        """stop() should terminate and wait for running process."""
        from agntrick.chat_cli import MCPServerManager

        manager = MCPServerManager()

        # Create mock process
        mock_process = MagicMock()
        manager.process = mock_process

        manager.stop()

        # Verify terminate and wait were called
        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called_once_with(timeout=5)

        # Process should be None after stop
        assert manager.process is None

    def test_stop_is_safe_when_no_process(self) -> None:
        """stop() should be safe to call when process is None."""
        from agntrick.chat_cli import MCPServerManager

        manager = MCPServerManager()
        manager.process = None

        # Should not raise
        manager.stop()

        # Process should still be None
        assert manager.process is None

    def test_stop_kills_process_group_on_sigterm_failure(self) -> None:
        """stop() should use os.killpg if process.terminate raises OSError."""
        from agntrick.chat_cli import MCPServerManager

        manager = MCPServerManager()

        # Create mock process that raises OSError on terminate
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.terminate.side_effect = OSError("Process already terminated")
        manager.process = mock_process

        with patch("os.killpg") as mock_killpg:
            with patch("os.getpgid", return_value=12345) as mock_getpgid:
                manager.stop()

                # Verify getpgid was called with the pid
                mock_getpgid.assert_called_once_with(mock_process.pid)

                # Verify killpg was called with the process group ID
                mock_killpg.assert_called_once_with(12345, 9)  # 9 = SIGKILL

        # Process should be None after stop
        assert manager.process is None

    def test_stop_force_kills_on_timeout(self) -> None:
        """stop() should call kill() if wait() times out."""
        from agntrick.chat_cli import MCPServerManager

        manager = MCPServerManager()

        # Create mock process that times out on first wait, succeeds on second
        mock_process = MagicMock()
        wait_call_count = [0]

        def wait_side_effect(**kwargs: object) -> None:
            wait_call_count[0] += 1
            if wait_call_count[0] == 1:
                raise subprocess.TimeoutExpired(cmd="test", timeout=5)
            # Second call after kill() succeeds

        mock_process.wait.side_effect = wait_side_effect
        manager.process = mock_process

        manager.stop()

        # Verify kill was called
        mock_process.kill.assert_called_once()

        # Verify wait was called twice (once after terminate, once after kill)
        assert mock_process.wait.call_count == 2

        # Process should be None after stop
        assert manager.process is None


class TestFindTestTenant:
    """Tests for find_test_tenant function."""

    def test_finds_test_tenant_from_config(self) -> None:
        """Should find tenant with id 'test' from config."""
        from agntrick.chat_cli import find_test_tenant

        # Create config with test tenant
        test_tenant = WhatsAppTenantConfig(
            id="test",
            phone="+1555123456",
            default_agent="assistant",
            allowed_contacts=["+1555999999"],
        )
        other_tenant = WhatsAppTenantConfig(
            id="production",
            phone="+1555987654",
            default_agent="developer",
            allowed_contacts=[],
        )
        config = AgntrickConfig()
        config.whatsapp.tenants = [other_tenant, test_tenant]

        result = find_test_tenant(config)

        assert result.id == "test"
        assert result.phone == "+1555123456"
        assert result.default_agent == "assistant"
        assert result.allowed_contacts == ["+1555999999"]

    def test_returns_default_when_not_configured(self) -> None:
        """Should return default tenant when 'test' tenant not in config."""
        from agntrick.chat_cli import find_test_tenant

        # Create config without test tenant
        config = AgntrickConfig()
        config.whatsapp.tenants = []

        result = find_test_tenant(config)

        assert result.id == "test"
        assert result.phone == "+1555000000"
        assert result.default_agent == "assistant"
        assert result.allowed_contacts == ["+1555000000"]

    def test_calls_get_config_when_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should call get_config() when config is None."""
        from agntrick.chat_cli import find_test_tenant

        # Create a mock config
        mock_config = AgntrickConfig()
        mock_config.whatsapp.tenants = []

        with patch("agntrick.chat_cli.get_config", return_value=mock_config) as mock_get_config:
            result = find_test_tenant(None)

            # Verify get_config was called
            mock_get_config.assert_called_once()

            # Should return default tenant
            assert result.id == "test"
            assert result.phone == "+1555000000"


class TestModuleConstants:
    """Tests for module-level constants."""

    def test_test_tenant_id_constant(self) -> None:
        """TEST_TENANT_ID should be 'test'."""
        from agntrick.chat_cli import TEST_TENANT_ID

        assert TEST_TENANT_ID == "test"

    def test_test_tenant_phone_constant(self) -> None:
        """TEST_TENANT_PHONE should be '+1555000000'."""
        from agntrick.chat_cli import TEST_TENANT_PHONE

        assert TEST_TENANT_PHONE == "+1555000000"

    def test_test_api_key_constant(self) -> None:
        """TEST_API_KEY should be 'test-secret'."""
        from agntrick.chat_cli import TEST_API_KEY

        assert TEST_API_KEY == "test-secret"

    def test_default_toolbox_port_constant(self) -> None:
        """DEFAULT_TOOLBOX_PORT should be 8080."""
        from agntrick.chat_cli import DEFAULT_TOOLBOX_PORT

        assert DEFAULT_TOOLBOX_PORT == 8080

    def test_mcp_startup_timeout_constant(self) -> None:
        """MCP_STARTUP_TIMEOUT should be 15."""
        from agntrick.chat_cli import MCP_STARTUP_TIMEOUT

        assert MCP_STARTUP_TIMEOUT == 15
