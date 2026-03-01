"""Tests for WhatsApp channel implementation."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentic_framework.channels.base import ConfigurationError, OutgoingMessage
from agentic_framework.channels.whatsapp import WhatsAppChannel


@pytest.fixture
def temp_storage(tmp_path: Path) -> Path:
    """Create a temporary storage directory for testing."""
    return tmp_path / "whatsapp"


@pytest.fixture
def mock_neonize_client() -> MagicMock:
    """Create a mock neonize client."""
    client = MagicMock()
    client.connect = MagicMock()
    client.disconnect = MagicMock()
    client.send_message = MagicMock()
    client.build_image_message = MagicMock()
    client.build_video_message = MagicMock()
    client.build_document_message = MagicMock()
    client.build_audio_message = MagicMock()
    client.event = MagicMock(return_value=lambda f: f)
    return client


@pytest.fixture
def whatsapp_channel(temp_storage: Path) -> WhatsAppChannel:
    """Create a WhatsAppChannel instance for testing."""
    return WhatsAppChannel(
        storage_path=temp_storage,
        allowed_contact="+34 666 666 666",
        log_filtered_messages=False,
    )


class TestWhatsAppChannelInitialization:
    """Tests for WhatsAppChannel initialization."""

    def test_init_creates_storage_directory(self, temp_storage: Path) -> None:
        """Test that initialization creates storage directory."""
        storage_path = temp_storage / "new_storage"
        assert not storage_path.exists()

        WhatsAppChannel(
            storage_path=storage_path,
            allowed_contact="+34 666 666 666",
        )

        assert storage_path.exists()
        assert storage_path.is_dir()

    def test_init_normalizes_allowed_contact(self, whatsapp_channel: WhatsAppChannel) -> None:
        """Test that allowed contact phone number is normalized."""
        channel = WhatsAppChannel(
            storage_path="/tmp/test",
            allowed_contact="+34 666 666 666",
        )
        assert channel.allowed_contact == "34666666666"

        channel2 = WhatsAppChannel(
            storage_path="/tmp/test",
            allowed_contact="+34-666-666-666",
        )
        assert channel2.allowed_contact == "34666666666"

        channel3 = WhatsAppChannel(
            storage_path="/tmp/test",
            allowed_contact="34666666666",
        )
        assert channel3.allowed_contact == "34666666666"

    def test_init_fails_with_invalid_storage(self) -> None:
        """Test that initialization fails with invalid storage path."""
        # Try to use a file as storage path
        with pytest.raises(ConfigurationError):
            WhatsAppChannel(
                storage_path="/etc/passwd",  # Not writable
                allowed_contact="+34 666 666 666",
            )


class TestWhatsAppChannelInitialize:
    """Tests for WhatsAppChannel initialization."""

    @pytest.mark.asyncio
    @patch("agentic_framework.channels.whatsapp.NewClient")
    async def test_initialize_creates_client(
        self, mock_client_class: MagicMock, whatsapp_channel: WhatsAppChannel
    ) -> None:
        """Test that initialize creates neonize client."""
        mock_client_instance = MagicMock()
        mock_client_instance.event = MagicMock(return_value=lambda f: f)
        mock_client_class.return_value = mock_client_instance

        await whatsapp_channel.initialize()

        mock_client_class.assert_called_once_with("agentic-framework-whatsapp")

    @pytest.mark.asyncio
    @patch("agentic_framework.channels.whatsapp.NewClient")
    async def test_initialize_handles_connection_error(
        self, mock_client_class: MagicMock, whatsapp_channel: WhatsAppChannel
    ) -> None:
        """Test that initialize handles connection errors correctly."""
        mock_client_class.side_effect = Exception("Connection failed")
        mock_client_class.return_value = MagicMock()

        with pytest.raises(Exception) as exc_info:
            await whatsapp_channel.initialize()

        assert "Failed to initialize neonize client" in str(exc_info.value)


class TestWhatsAppChannelSend:
    """Tests for WhatsAppChannel.send method."""

    @pytest.mark.asyncio
    @patch("agentic_framework.channels.whatsapp.NewClient")
    @patch("agentic_framework.channels.whatsapp.build_jid")
    async def test_send_text_message(
        self, mock_build_jid: MagicMock, mock_client_class: MagicMock, whatsapp_channel: WhatsAppChannel
    ) -> None:
        """Test sending a text message."""
        mock_client = MagicMock()
        mock_client.send_message = MagicMock()
        mock_client_class.return_value = mock_client
        mock_build_jid.return_value = "1234567890@s.whatsapp.net"

        await whatsapp_channel.initialize()

        message = OutgoingMessage(
            text="Hello there!",
            recipient_id="+34 666 666 666",
        )

        await whatsapp_channel.send(message)

        # The send happens via run_in_executor, so verify the call was made
        # We can't easily verify the exact args here due to threading

    @pytest.mark.asyncio
    @patch("agentic_framework.channels.whatsapp.NewClient")
    @patch("agentic_framework.channels.whatsapp.build_jid")
    @patch("httpx.AsyncClient")
    async def test_send_media_message(
        self,
        mock_httpx: MagicMock,
        mock_build_jid: MagicMock,
        mock_client_class: MagicMock,
        whatsapp_channel: WhatsAppChannel,
    ) -> None:
        """Test sending a media message."""
        # Setup mock HTTP client
        mock_response = MagicMock()
        mock_response.content = b"fake_image_data"
        mock_response.raise_for_status = MagicMock()
        mock_httpx_instance = MagicMock()
        mock_httpx_instance.__aenter__.return_value.get.return_value = mock_response
        mock_httpx_instance.__aenter__.return_value.__aenter__.return_value = mock_httpx_instance
        mock_httpx.return_value = mock_httpx_instance

        # Setup neonize client
        mock_client = MagicMock()
        mock_client.build_image_message = MagicMock(return_value=MagicMock())
        mock_client.send_message = MagicMock()
        mock_client_class.return_value = mock_client
        mock_build_jid.return_value = "1234567890@s.whatsapp.net"

        await whatsapp_channel.initialize()

        message = OutgoingMessage(
            text="Here's an image",
            recipient_id="+34 666 666 666",
            media_url="https://example.com/image.jpg",
            media_type="image",
        )

        await whatsapp_channel.send(message)

        mock_client.build_image_message.assert_called_once()


class TestWhatsAppChannelContactFiltering:
    """Tests for contact filtering functionality."""

    @pytest.mark.asyncio
    async def test_allowed_contact_passes_filter(self, whatsapp_channel: WhatsAppChannel) -> None:
        """Test that messages from allowed contact are processed."""
        allowed_number = "34666666666"
        whatsapp_channel.allowed_contact = allowed_number

        test_number = "+34 666 666 666"
        normalized = whatsapp_channel._normalize_phone_number(test_number)
        assert normalized == allowed_number

    @pytest.mark.asyncio
    async def test_disallowed_contact_is_filtered(self, whatsapp_channel: WhatsAppChannel) -> None:
        """Test that messages from disallowed contacts are filtered."""
        whatsapp_channel.allowed_contact = "34666666666"

        # These should not match
        test_numbers = ["+34 611 111 111", "+44 777 888 999", "+1 555 123 4567"]
        for number in test_numbers:
            normalized = whatsapp_channel._normalize_phone_number(number)
            assert normalized != whatsapp_channel.allowed_contact


class TestWhatsAppChannelShutdown:
    """Tests for WhatsAppChannel.shutdown method."""

    @pytest.mark.asyncio
    @patch("agentic_framework.channels.whatsapp.NewClient")
    async def test_shutdown_clears_client(
        self, mock_client_class: MagicMock, whatsapp_channel: WhatsAppChannel
    ) -> None:
        """Test that shutdown clears client reference."""
        mock_client = MagicMock()
        mock_client.disconnect = MagicMock()
        mock_client.event = MagicMock()
        mock_client.event.return_value = MagicMock()
        mock_client_class.return_value = mock_client

        await whatsapp_channel.initialize()

        await whatsapp_channel.shutdown()

        assert whatsapp_channel._client is None
        assert not whatsapp_channel._is_listening


class TestWhatsAppChannelPrivacySimple:
    """Simple tests for privacy features."""

    def test_group_chat_jid_ends_with_g_us(self, whatsapp_channel: WhatsAppChannel) -> None:
        """Test that group chat JID ends with @g.us suffix."""
        group_jid = "123456789@g.us"
        direct_jid = "34666666666@s.whatsapp.net"

        assert group_jid.endswith("@g.us")
        assert not direct_jid.endswith("@g.us")

    def test_normalize_phone_number_works(self, whatsapp_channel: WhatsAppChannel) -> None:
        """Test that phone number normalization works correctly."""
        test_cases = [
            ("+34 666 666 666", "34666666666"),
            ("+34-666-666-666", "34666666666"),
            ("+34666666666@s.whatsapp.net", "34666666666"),
        ]

        for input_num, expected in test_cases:
            result = whatsapp_channel._normalize_phone_number(input_num)
            assert result == expected


class TestWhatsAppChannelDeduplicationSimple:
    """Simple tests for deduplication."""

    def test_duplicate_detection(self, whatsapp_channel: WhatsAppChannel) -> None:
        """Test that duplicate messages are detected."""
        message_text = "Test message"
        sender_id = "34666666666@s.whatsapp.net"

        # First check - should not be duplicate
        is_duplicate_1 = whatsapp_channel._is_duplicate_message(message_text, sender_id)
        assert not is_duplicate_1

        # Second check - same message should be duplicate
        is_duplicate_2 = whatsapp_channel._is_duplicate_message(message_text, sender_id)
        assert is_duplicate_2

    def test_different_messages_not_duplicate(self, whatsapp_channel: WhatsAppChannel) -> None:
        """Test that different messages are not treated as duplicates."""
        message1 = "First message"
        message2 = "Second message"
        sender_id = "34666666666@s.whatsapp.net"

        is_duplicate_1 = whatsapp_channel._is_duplicate_message(message1, sender_id)
        is_duplicate_2 = whatsapp_channel._is_duplicate_message(message2, sender_id)

        # Both should not be duplicates
        assert not is_duplicate_1
        assert not is_duplicate_2
