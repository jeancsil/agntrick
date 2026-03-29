"""Tests for WhatsApp QR code and status endpoints."""

from fastapi.testclient import TestClient


class TestWhatsAppQREndpoints:
    """Tests for WhatsApp QR code endpoints."""

    def test_receive_qr_code_stores_it(self) -> None:
        """QR code POST endpoint should store the QR code."""
        from agntrick.api.server import create_app

        app = create_app()
        client = TestClient(app)

        response = client.post(
            "/api/v1/whatsapp/qr/test-tenant",
            json={"image": "base64encodedimage"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "message" in data

    def test_receive_qr_code_invalid_payload(self) -> None:
        """QR code POST endpoint should reject invalid payload."""
        from agntrick.api.server import create_app

        app = create_app()
        client = TestClient(app)

        response = client.post(
            "/api/v1/whatsapp/qr/test-tenant",
            json={},  # Missing image field
        )

        assert response.status_code == 422  # Validation error

    def test_qr_page_returns_html(self) -> None:
        """QR page endpoint should return HTML."""
        from agntrick.api.server import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/api/v1/whatsapp/qr/test-tenant/page")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        content = response.text
        assert "WhatsApp QR Code" in content
        assert "test-tenant" in content

    # Note: SSE testing (test_qr_stream_returns_sse) is better suited for integration tests
    # and is skipped here to avoid hanging unit tests


class TestWhatsAppStatusEndpoints:
    """Tests for WhatsApp status endpoints."""

    def test_receive_connected_status(self) -> None:
        """Status endpoint should store connected status."""
        from agntrick.api.server import create_app

        app = create_app()
        client = TestClient(app)

        response = client.post(
            "/api/v1/whatsapp/status/test-tenant",
            json={"status": "connected", "phone": "+1234567890"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "message" in data

    def test_receive_disconnected_status(self) -> None:
        """Status endpoint should store disconnected status."""
        from agntrick.api.server import create_app

        app = create_app()
        client = TestClient(app)

        response = client.post(
            "/api/v1/whatsapp/status/test-tenant",
            json={"status": "disconnected"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_receive_status_invalid_payload(self) -> None:
        """Status endpoint should reject invalid payload."""
        from agntrick.api.server import create_app

        app = create_app()
        client = TestClient(app)

        response = client.post(
            "/api/v1/whatsapp/status/test-tenant",
            json={},  # Missing status field
        )

        assert response.status_code == 422  # Validation error

    def test_receive_connected_status_without_phone(self) -> None:
        """Status endpoint should accept connected status without phone."""
        from agntrick.api.server import create_app

        app = create_app()
        client = TestClient(app)

        response = client.post(
            "/api/v1/whatsapp/status/test-tenant",
            json={"status": "connected"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
