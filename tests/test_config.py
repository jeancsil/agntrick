"""Tests for unified configuration."""

from pathlib import Path

import pytest
import yaml


class TestUnifiedConfig:
    """Tests for unified configuration loading."""

    def test_config_loads_all_sections(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Config should load all required sections."""
        config_file = tmp_path / ".agntrick.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "llm": {"provider": "openai", "model": "gpt-4", "temperature": 0.5},
                    "api": {"host": "0.0.0.0", "port": 9000},
                    "storage": {"base_path": str(tmp_path / "data")},
                    "auth": {"api_keys": {"test-key": "tenant-1"}},
                }
            )
        )

        monkeypatch.setenv("AGNTRICK_CONFIG", str(config_file))
        from agntrick.config import get_config

        config = get_config(force_reload=True)

        assert config.llm.provider == "openai"
        assert config.llm.temperature == 0.5
        assert config.api.port == 9000
        assert "test-key" in config.auth.api_keys

    def test_config_loads_whatsapp_tenants(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Config should load WhatsApp tenant configurations."""
        config_file = tmp_path / ".agntrick.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "whatsapp": {
                        "tenants": [
                            {"id": "personal", "phone": "+34611111111", "default_agent": "developer"},
                            {"id": "work", "phone": "+34622222222", "default_agent": "chef"},
                        ]
                    }
                }
            )
        )

        monkeypatch.setenv("AGNTRICK_CONFIG", str(config_file))
        from agntrick.config import get_config

        config = get_config(force_reload=True)

        assert len(config.whatsapp.tenants) == 2
        assert config.whatsapp.tenants[0].id == "personal"
        assert config.whatsapp.tenants[0].phone == "+34611111111"

    def test_config_get_tenant_by_phone(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_tenant_by_phone should return correct tenant."""
        config_file = tmp_path / ".agntrick.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "whatsapp": {
                        "tenants": [
                            {"id": "personal", "phone": "+34611111111"},
                        ]
                    }
                }
            )
        )

        monkeypatch.setenv("AGNTRICK_CONFIG", str(config_file))
        from agntrick.config import get_config

        config = get_config(force_reload=True)

        tenant = config.whatsapp.get_tenant_by_phone("+34611111111")
        assert tenant is not None
        assert tenant.id == "personal"

        assert config.whatsapp.get_tenant_by_phone("+99999999999") is None

    def test_config_get_tenant_db_path_sanitizes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_tenant_db_path should sanitize tenant IDs."""
        config_file = tmp_path / ".agntrick.yaml"
        config_file.write_text(yaml.dump({"storage": {"base_path": str(tmp_path / "data")}}))

        monkeypatch.setenv("AGNTRICK_CONFIG", str(config_file))
        from agntrick.config import get_config

        config = get_config(force_reload=True)

        path = config.storage.get_tenant_db_path("../../../etc/passwd")
        assert ".." not in str(path)
        assert "passwd" in str(path)  # Only alphanumeric chars kept

    def test_config_missing_sections_get_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Missing sections should get sensible defaults."""
        monkeypatch.setenv("AGNTRICK_CONFIG", "__nonexistent__")
        from agntrick.config import get_config

        config = get_config(force_reload=True)

        assert config.api.host == "127.0.0.1"
        assert config.api.port == 8000
        assert config.auth.api_keys == {}
        assert config.whatsapp.tenants == []
