"""Tests for WhatsApp audio message endpoint."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from agntrick.api.server import create_app  # type: ignore[import-untyped]


class TestAudioRoute:
    """Tests for the /api/v1/channels/whatsapp/audio endpoint."""

    @patch("agntrick.api.routes.whatsapp.get_whatsapp_registry")
    @patch("agntrick.api.routes.whatsapp.get_config")
    def test_audio_endpoint_missing_api_key(self, mock_config: MagicMock, mock_registry: MagicMock) -> None:
        """Test that missing API key returns 401."""
        mock_config.return_value = MagicMock(auth=MagicMock(api_keys={"test-key": "tenant1"}))
        app = create_app()
        client = TestClient(app)
        response = client.post(
            "/api/v1/channels/whatsapp/audio",
            files={"audio": ("test.ogg", b"audio data", "audio/ogg")},
            data={"tenant_id": "t1", "phone": "1234567890", "mime_type": "audio/ogg"},
        )
        assert response.status_code == 401

    @patch("agntrick.api.routes.whatsapp.get_config")
    def test_audio_endpoint_no_audio_file(self, mock_config: MagicMock) -> None:
        """Test that missing audio file returns 400."""
        mock_config.return_value = MagicMock(auth=MagicMock(api_keys={"test-key": "tenant1"}))
        app = create_app()
        client = TestClient(app)
        response = client.post(
            "/api/v1/channels/whatsapp/audio",
            headers={"X-API-Key": "test-key"},
            data={"tenant_id": "t1", "phone": "1234567890"},
        )
        assert response.status_code == 400

    @patch("agntrick.api.routes.whatsapp.get_whatsapp_registry")
    @patch("agntrick.api.routes.whatsapp.get_config")
    def test_audio_endpoint_missing_phone(self, mock_config: MagicMock, mock_registry: MagicMock) -> None:
        """Test that missing phone returns 400."""
        mock_config.return_value = MagicMock(auth=MagicMock(api_keys={"test-key": "tenant1"}))
        app = create_app()
        client = TestClient(app)
        response = client.post(
            "/api/v1/channels/whatsapp/audio",
            headers={"X-API-Key": "test-key"},
            files={"audio": ("test.ogg", b"audio data", "audio/ogg")},
            data={"tenant_id": "t1"},
        )
        assert response.status_code == 400

    @patch("agntrick.api.routes.whatsapp.get_whatsapp_registry")
    @patch("agntrick.api.routes.whatsapp.get_config")
    def test_audio_endpoint_tenant_not_found(self, mock_config: MagicMock, mock_registry: MagicMock) -> None:
        """Test that unknown phone returns 404."""
        mock_config.return_value = MagicMock(
            auth=MagicMock(api_keys={"test-key": "tenant1"}),
            whatsapp=MagicMock(tenants=[]),
        )
        mock_registry_instance = MagicMock()
        mock_registry_instance.lookup_by_phone.return_value = None
        mock_registry.return_value = mock_registry_instance

        app = create_app()
        client = TestClient(app)
        response = client.post(
            "/api/v1/channels/whatsapp/audio",
            headers={"X-API-Key": "test-key"},
            files={"audio": ("test.ogg", b"audio data", "audio/ogg")},
            data={"phone": "9999999999", "mime_type": "audio/ogg"},
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
