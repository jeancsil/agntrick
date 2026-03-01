"""Tests for WhatsApp channel implementation."""

from pathlib import Path
from typing import Any
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

        # The send happens via run_in_executor, so verify it was called
        # We can't easily verify exact args here due to threading

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

    @pytest.mark.asyncio
    @patch("agentic_framework.channels.whatsapp.NewClient")
    @patch("asyncio.run_coroutine_threadsafe")
    async def test_allowed_contact_message_processed(
        self, mock_run_coro: MagicMock, mock_client_class: MagicMock, whatsapp_channel: WhatsAppChannel
    ) -> None:
        """Test that messages from allowed contact are processed and callback is invoked."""
        whatsapp_channel.allowed_contact = "34666666666"

        # Capture scheduled callbacks
        scheduled_coroutines: list = []

        def capture_run_coro(coro, loop):
            scheduled_coroutines.append(coro)
            return MagicMock()

        mock_run_coro.side_effect = capture_run_coro

        # Set up the callback and loop (required by _on_message_event)
        async def mock_callback(msg):
            pass

        whatsapp_channel._message_callback = mock_callback
        whatsapp_channel._loop = MagicMock()

        # Create a mock message event from allowed contact
        mock_event = MagicMock()
        mock_event.Message.conversation = "Hello!"
        mock_event.Info.MessageSource.Sender = "34666666666@s.whatsapp.net"
        mock_event.Info.MessageSource.Chat = "34666666666@s.whatsapp.net"
        mock_event.Info.MessageSource.IsFromMe = False
        mock_event.Info.Timestamp = 1234567890

        # Mock Jid2String to return the JID
        with patch("agentic_framework.channels.whatsapp.Jid2String", side_effect=lambda x: str(x)):
            # Call the message event handler
            whatsapp_channel._on_message_event(mock_client_class.return_value, mock_event)

        # Verify a coroutine was scheduled
        assert len(scheduled_coroutines) == 1
        # Execute the scheduled callback
        await scheduled_coroutines[0]

    @pytest.mark.asyncio
    @patch("agentic_framework.channels.whatsapp.NewClient")
    @patch("asyncio.run_coroutine_threadsafe")
    async def test_disallowed_contact_message_filtered(
        self, mock_run_coro: MagicMock, mock_client_class: MagicMock, whatsapp_channel: WhatsAppChannel
    ) -> None:
        """Test that messages from disallowed contacts are NOT processed."""
        whatsapp_channel.allowed_contact = "34666666666"

        scheduled_coroutines: list = []

        def capture_run_coro(coro, loop):
            scheduled_coroutines.append(coro)
            return MagicMock()

        mock_run_coro.side_effect = capture_run_coro

        # Set up the callback and loop (required by _on_message_event)
        async def mock_callback(msg):
            pass

        whatsapp_channel._message_callback = mock_callback
        whatsapp_channel._loop = MagicMock()

        # Create a mock message event from a DISALLOWED contact
        mock_event = MagicMock()
        mock_event.Message.conversation = "This should be ignored!"
        mock_event.Info.MessageSource.Sender = "196859943489627@lid"
        mock_event.Info.MessageSource.Chat = "196859943489627@lid"
        mock_event.Info.MessageSource.IsFromMe = False
        mock_event.Info.Timestamp = 1234567890

        with patch("agentic_framework.channels.whatsapp.Jid2String", side_effect=lambda x: str(x)):
            whatsapp_channel._on_message_event(mock_client_class.return_value, mock_event)

        # Verify NO coroutine was scheduled (message was filtered)
        assert len(scheduled_coroutines) == 0

    @pytest.mark.asyncio
    @patch("agentic_framework.channels.whatsapp.NewClient")
    @patch("asyncio.run_coroutine_threadsafe")
    async def test_self_message_from_disallowed_lid_is_processed(
        self, mock_run_coro: MagicMock, mock_client_class: MagicMock, whatsapp_channel: WhatsAppChannel
    ) -> None:
        """Test that self-messages from LIDs (even if not matching allowed_contact) are processed.

        With the new security model, self-messages are allowed to enable legitimate
        self-messaging use case. The security guarantee is that responses go back to
        the original sender (the LID), not to the allowed_contact. This prevents
        the agent from being "hijacked" to respond to the wrong contact.

        The original security concern was that messages from UNKNOWN devices could get responses.
        Self-messages from the same device don't pose this risk because:
        1. Responses go back to the original sender JID
        2. You can't "steal" your own self-messages
        """
        whatsapp_channel.allowed_contact = "34666666666"  # User's actual number

        scheduled_coroutines: list = []

        def capture_run_coro(coro, loop):
            scheduled_coroutines.append(coro)
            return MagicMock()

        mock_run_coro.side_effect = capture_run_coro

        # Set up the callback and loop (required by _on_message_event)
        async def mock_callback(msg):
            pass

        whatsapp_channel._message_callback = mock_callback
        whatsapp_channel._loop = MagicMock()

        # Create a mock self-message event from a DIFFERENT LID (IsFromMe=True)
        # This simulates messaging from a different device or context
        mock_event = MagicMock()
        mock_event.Message.conversation = "Testing self-message from different device"
        mock_event.Info.MessageSource.Sender = "196859943489627@lid"  # Different LID
        mock_event.Info.MessageSource.Chat = "196859943489627@lid"
        mock_event.Info.MessageSource.IsFromMe = True  # Self-message from device
        mock_event.Info.Timestamp = 1234567890

        with patch("agentic_framework.channels.whatsapp.Jid2String", side_effect=lambda x: str(x)):
            whatsapp_channel._on_message_event(mock_client_class.return_value, mock_event)

        # Verify a coroutine was scheduled (self-messages are now allowed)
        assert len(scheduled_coroutines) == 1

        # Execute the callback to capture the IncomingMessage
        captured_message: Any = None

        async def capture_callback(msg):
            nonlocal captured_message
            captured_message = msg

        whatsapp_channel._message_callback = capture_callback
        await scheduled_coroutines[0]

        # CRITICAL: Verify that the response would go back to the original LID,
        # NOT to the allowed_contact phone number. This is the key security guarantee.
        assert captured_message is not None
        assert captured_message.sender_id == "196859943489627@lid"  # Back to original LID
        assert captured_message.sender_id != "34666666666@s.whatsapp.net"  # NOT to allowed_contact

    @pytest.mark.asyncio
    @patch("agentic_framework.channels.whatsapp.NewClient")
    @patch("asyncio.run_coroutine_threadsafe")
    async def test_self_message_from_allowed_contact_is_processed(
        self, mock_run_coro: MagicMock, mock_client_class: MagicMock, whatsapp_channel: WhatsAppChannel
    ) -> None:
        """Test that self-messages from the allowed contact number ARE processed."""
        whatsapp_channel.allowed_contact = "34666666666"  # User sets their own number

        scheduled_coroutines: list = []

        def capture_run_coro(coro, loop):
            scheduled_coroutines.append(coro)
            return MagicMock()

        mock_run_coro.side_effect = capture_run_coro

        # Set up the callback and loop (required by _on_message_event)
        async def mock_callback(msg):
            pass

        whatsapp_channel._message_callback = mock_callback
        whatsapp_channel._loop = MagicMock()

        # Create a self-message event matching the allowed contact
        mock_event = MagicMock()
        mock_event.Message.conversation = "Hello myself!"
        mock_event.Info.MessageSource.Sender = "34666666666@s.whatsapp.net"
        mock_event.Info.MessageSource.Chat = "34666666666@s.whatsapp.net"
        mock_event.Info.MessageSource.IsFromMe = True
        mock_event.Info.Timestamp = 1234567890

        with patch("agentic_framework.channels.whatsapp.Jid2String", side_effect=lambda x: str(x)):
            whatsapp_channel._on_message_event(mock_client_class.return_value, mock_event)

        # Verify a coroutine was scheduled (self-message from allowed contact)
        assert len(scheduled_coroutines) == 1
        # Execute the scheduled callback
        await scheduled_coroutines[0]

    @pytest.mark.asyncio
    @patch("agentic_framework.channels.whatsapp.NewClient")
    @patch("asyncio.run_coroutine_threadsafe")
    async def test_group_chat_always_filtered(
        self, mock_run_coro: MagicMock, mock_client_class: MagicMock, whatsapp_channel: WhatsAppChannel
    ) -> None:
        """Test that group chat messages are ALWAYS filtered regardless of contact."""
        whatsapp_channel.allowed_contact = "34666666666"
        whatsapp_channel.log_filtered_messages = True

        scheduled_coroutines: list = []

        def capture_run_coro(coro, loop):
            scheduled_coroutines.append(coro)
            return MagicMock()

        mock_run_coro.side_effect = capture_run_coro

        # Set up the callback and loop (required by _on_message_event)
        async def mock_callback(msg):
            pass

        whatsapp_channel._message_callback = mock_callback
        whatsapp_channel._loop = MagicMock()

        # Create a group chat message event
        mock_event = MagicMock()
        mock_event.Message.conversation = "Group message"
        mock_event.Info.MessageSource.Sender = "34666666666@s.whatsapp.net"  # Even from allowed contact
        mock_event.Info.MessageSource.Chat = "123456789@g.us"  # GROUP CHAT JID
        mock_event.Info.MessageSource.IsFromMe = False
        mock_event.Info.Timestamp = 1234567890

        with patch("agentic_framework.channels.whatsapp.Jid2String", side_effect=lambda x: str(x)):
            whatsapp_channel._on_message_event(mock_client_class.return_value, mock_event)

        # Group chats should ALWAYS be filtered - no coroutine scheduled
        assert len(scheduled_coroutines) == 0

    @pytest.mark.asyncio
    @patch("agentic_framework.channels.whatsapp.NewClient")
    @patch("asyncio.run_coroutine_threadsafe")
    async def test_lid_format_allowed_contact(
        self, mock_run_coro: MagicMock, mock_client_class: MagicMock, whatsapp_channel: WhatsAppChannel
    ) -> None:
        """Test that LID format numbers work as allowed contacts."""
        # Allow an LID number
        whatsapp_channel.allowed_contact = "118657162162293"

        scheduled_coroutines: list = []

        def capture_run_coro(coro, loop):
            scheduled_coroutines.append(coro)
            return MagicMock()

        mock_run_coro.side_effect = capture_run_coro

        # Set up the callback and loop (required by _on_message_event)
        async def mock_callback(msg):
            pass

        whatsapp_channel._message_callback = mock_callback
        whatsapp_channel._loop = MagicMock()

        # Create a message from the LID contact
        mock_event = MagicMock()
        mock_event.Message.conversation = "Message from LID contact"
        mock_event.Info.MessageSource.Sender = "118657162162293@lid"
        mock_event.Info.MessageSource.Chat = "118657162162293@lid"
        mock_event.Info.MessageSource.IsFromMe = False
        mock_event.Info.Timestamp = 1234567890

        with patch("agentic_framework.channels.whatsapp.Jid2String", side_effect=lambda x: str(x)):
            whatsapp_channel._on_message_event(mock_client_class.return_value, mock_event)

        # Verify a coroutine was scheduled
        assert len(scheduled_coroutines) == 1
        # Execute the scheduled callback
        await scheduled_coroutines[0]

    @pytest.mark.asyncio
    @patch("agentic_framework.channels.whatsapp.NewClient")
    @patch("asyncio.run_coroutine_threadsafe")
    async def test_multiple_disallowed_contacts_all_filtered(
        self, mock_run_coro: MagicMock, mock_client_class: MagicMock, whatsapp_channel: WhatsAppChannel
    ) -> None:
        """Test that multiple disallowed contacts are all filtered."""
        whatsapp_channel.allowed_contact = "34666666666"

        scheduled_coroutines: list = []

        def capture_run_coro(coro, loop):
            scheduled_coroutines.append(coro)
            return MagicMock()

        mock_run_coro.side_effect = capture_run_coro

        # Set up the callback and loop (required by _on_message_event)
        async def mock_callback(msg):
            pass

        whatsapp_channel._message_callback = mock_callback
        whatsapp_channel._loop = MagicMock()

        # Test multiple disallowed contacts
        disallowed_jids = [
            "196859943489627@lid",
            "1234567890@s.whatsapp.net",
            "44777888999@s.whatsapp.net",
            "15551234567@s.whatsapp.net",
        ]

        for jid in disallowed_jids:
            mock_event = MagicMock()
            mock_event.Message.conversation = f"Message from {jid}"
            mock_event.Info.MessageSource.Sender = jid
            mock_event.Info.MessageSource.Chat = jid
            mock_event.Info.MessageSource.IsFromMe = False
            mock_event.Info.Timestamp = 1234567890

            with patch("agentic_framework.channels.whatsapp.Jid2String", return_value=jid):
                whatsapp_channel._on_message_event(mock_client_class.return_value, mock_event)

        # Verify NO coroutines were scheduled (all messages filtered)
        assert len(scheduled_coroutines) == 0

    @pytest.mark.asyncio
    @patch("agentic_framework.channels.whatsapp.NewClient")
    @patch("asyncio.run_coroutine_threadsafe")
    async def test_user_real_world_scenario_self_message_from_lid(
        self, mock_run_coro: MagicMock, mock_client_class: MagicMock, whatsapp_channel: WhatsAppChannel
    ) -> None:
        """Test the exact scenario user encountered: self-message from LID not matching phone number.

        This reproduces the real-world scenario where:
        1. User sets allowed_contact to their phone number (+34 677 427 318)
        2. User sends a message to themselves from their phone
        3. Message arrives from device's LID (118657162162293@lid)
        4. LID doesn't match phone number (118657162162293 != 34677427318)
        5. But is_from_me=True, so message should be ALLOWED
        6. Response should go back to the LID, not the phone number

        This test ensures this scenario works without manual testing.
        """
        # User's actual phone number as in config
        whatsapp_channel.allowed_contact = "34677427318"

        scheduled_coroutines: list = []

        def capture_run_coro(coro, loop):
            scheduled_coroutines.append(coro)
            return MagicMock()

        mock_run_coro.side_effect = capture_run_coro

        async def mock_callback(msg):
            pass

        whatsapp_channel._message_callback = mock_callback
        whatsapp_channel._loop = MagicMock()

        # Exact scenario from user's logs:
        # - Message from LID 118657162162293@lid
        # - IsFromMe=True (self-message)
        # - allowed_contact is phone number 34677427318
        mock_event = MagicMock()
        mock_event.Message.conversation = "Test message"
        mock_event.Info.MessageSource.Sender = "118657162162293@lid"
        mock_event.Info.MessageSource.Chat = "118657162162293@lid"
        mock_event.Info.MessageSource.IsFromMe = True
        mock_event.Info.Timestamp = 1234567890

        with patch("agentic_framework.channels.whatsapp.Jid2String", return_value="118657162162293@lid"):
            whatsapp_channel._on_message_event(mock_client_class.return_value, mock_event)

        # Message should be processed (is_from_me=True allows self-messages)
        assert len(scheduled_coroutines) == 1, "Self-message from LID should be processed"

        # Verify response routing: response should go back to original LID
        captured_message: Any = None

        async def capture_callback(msg):
            nonlocal captured_message
            captured_message = msg

        whatsapp_channel._message_callback = capture_callback
        await scheduled_coroutines[0]

        assert captured_message is not None
        assert captured_message.sender_id == "118657162162293@lid", (
            "Response should go back to original LID, not to phone number"
        )
        # Verify it's NOT going to the phone number
        assert "34677427318" not in captured_message.sender_id, (
            "Response should NOT be routed to phone number when self-messaging"
        )

    @pytest.mark.asyncio
    @patch("agentic_framework.channels.whatsapp.NewClient")
    @patch("asyncio.run_coroutine_threadsafe")
    async def test_self_message_response_routing_always_to_original_sender(
        self, mock_run_coro: MagicMock, mock_client_class: MagicMock, whatsapp_channel: WhatsAppChannel
    ) -> None:
        """Test that self-message responses ALWAYS go back to original sender LID.

        This is a critical security test: even if someone self-messages from
        a LID that doesn't match allowed_contact, the response must
        go back to that same LID, never to the allowed_contact.

        This prevents a scenario where:
        1. Attacker from device A sends self-message with LID A
        2. Agent processes message (is_from_me=True)
        3. Response could potentially be redirected to allowed_contact (phone number)
        4. This would expose the agent's responses to the attacker

        The fix ensures responses always echo back to the original sender.
        """
        whatsapp_channel.allowed_contact = "34666666666"

        scheduled_coroutines: list = []

        def capture_run_coro(coro, loop):
            scheduled_coroutines.append(coro)
            return MagicMock()

        mock_run_coro.side_effect = capture_run_coro

        async def mock_callback(msg):
            pass

        whatsapp_channel._message_callback = mock_callback
        whatsapp_channel._loop = MagicMock()

        # Self-message from LID that doesn't match phone number
        mock_event = MagicMock()
        mock_event.Message.conversation = "Test"
        mock_event.Info.MessageSource.Sender = "999888888888@lid"  # Random LID
        mock_event.Info.MessageSource.Chat = "999888888888@lid"
        mock_event.Info.MessageSource.IsFromMe = True
        mock_event.Info.Timestamp = 1234567890

        with patch("agentic_framework.channels.whatsapp.Jid2String", return_value="999888888888@lid"):
            whatsapp_channel._on_message_event(mock_client_class.return_value, mock_event)

        assert len(scheduled_coroutines) == 1

        captured_message: Any = None

        async def capture_callback(msg):
            nonlocal captured_message
            captured_message = msg

        whatsapp_channel._message_callback = capture_callback
        await scheduled_coroutines[0]

        # CRITICAL SECURITY CHECK: Response must go back to original LID
        assert captured_message.sender_id == "999888888888@lid"
        # NOT to the phone number (preventing response hijacking)
        assert "34666666666" not in captured_message.sender_id

    @pytest.mark.asyncio
    @patch("agentic_framework.channels.whatsapp.NewClient")
    @patch("asyncio.run_coroutine_threadsafe")
    async def test_regular_external_message_from_allowed_contact(
        self, mock_run_coro: MagicMock, mock_client_class: MagicMock, whatsapp_channel: WhatsAppChannel
    ) -> None:
        """Test that regular external messages from allowed contact work.

        This covers the normal use case where someone (not the user themselves)
        sends a message from the phone number configured as allowed_contact.
        """
        whatsapp_channel.allowed_contact = "34666666666"

        scheduled_coroutines: list = []

        def capture_run_coro(coro, loop):
            scheduled_coroutines.append(coro)
            return MagicMock()

        mock_run_coro.side_effect = capture_run_coro

        async def mock_callback(msg):
            pass

        whatsapp_channel._message_callback = mock_callback
        whatsapp_channel._loop = MagicMock()

        # Regular message from phone number (not self-message)
        mock_event = MagicMock()
        mock_event.Message.conversation = "Hello from external contact"
        mock_event.Info.MessageSource.Sender = "34666666666@s.whatsapp.net"
        mock_event.Info.MessageSource.Chat = "34666666666@s.whatsapp.net"
        mock_event.Info.MessageSource.IsFromMe = False  # NOT a self-message
        mock_event.Info.Timestamp = 1234567890

        with patch("agentic_framework.channels.whatsapp.Jid2String", return_value="34666666666@s.whatsapp.net"):
            whatsapp_channel._on_message_event(mock_client_class.return_value, mock_event)

        # Should be processed (matches allowed_contact, not self-message so passes strict check)
        assert len(scheduled_coroutines) == 1

    @pytest.mark.asyncio
    @patch("agentic_framework.channels.whatsapp.NewClient")
    @patch("asyncio.run_coroutine_threadsafe")
    async def test_external_message_from_disallowed_contact_filtered(
        self, mock_run_coro: MagicMock, mock_client_class: MagicMock, whatsapp_channel: WhatsAppChannel
    ) -> None:
        """Test that external messages from disallowed contacts are filtered.

        This is the core security feature: only the configured allowed_contact
        can send messages to the agent. All other senders are blocked.
        """
        whatsapp_channel.allowed_contact = "34666666666"

        scheduled_coroutines: list = []

        def capture_run_coro(coro, loop):
            scheduled_coroutines.append(coro)
            return MagicMock()

        mock_run_coro.side_effect = capture_run_coro

        async def mock_callback(msg):
            pass

        whatsapp_channel._message_callback = mock_callback
        whatsapp_channel._loop = MagicMock()

        # Message from different phone number
        mock_event = MagicMock()
        mock_event.Message.conversation = "Unauthorized message"
        mock_event.Info.MessageSource.Sender = "1234567890@s.whatsapp.net"
        mock_event.Info.MessageSource.Chat = "1234567890@s.whatsapp.net"
        mock_event.Info.MessageSource.IsFromMe = False
        mock_event.Info.Timestamp = 1234567890

        with patch("agentic_framework.channels.whatsapp.Jid2String", return_value="1234567890@s.whatsapp.net"):
            whatsapp_channel._on_message_event(mock_client_class.return_value, mock_event)

        # Should be filtered (doesn't match allowed_contact and is_from_me=False)
        assert len(scheduled_coroutines) == 0, "Disallowed external contact should be filtered"

    @pytest.mark.asyncio
    @patch("agentic_framework.channels.whatsapp.NewClient")
    @patch("asyncio.run_coroutine_threadsafe")
    async def test_group_chat_from_allowed_contact_always_filtered(
        self, mock_run_coro: MagicMock, mock_client_class: MagicMock, whatsapp_channel: WhatsAppChannel
    ) -> None:
        """Test that group chat messages are ALWAYS filtered, even from allowed contact.

        This is an absolute security rule: no group chat messages are ever processed,
        regardless of whether the sender is the allowed_contact or not.
        """
        whatsapp_channel.allowed_contact = "34666666666"

        scheduled_coroutines: list = []

        def capture_run_coro(coro, loop):
            scheduled_coroutines.append(coro)
            return MagicMock()

        mock_run_coro.side_effect = capture_run_coro

        async def mock_callback(msg):
            pass

        whatsapp_channel._message_callback = mock_callback
        whatsapp_channel._loop = MagicMock()

        # Group chat message even from allowed contact
        mock_event = MagicMock()
        mock_event.Message.conversation = "Group message"
        mock_event.Info.MessageSource.Sender = "34666666666@s.whatsapp.net"
        mock_event.Info.MessageSource.Chat = "123456789@g.us"  # GROUP CHAT JID
        mock_event.Info.MessageSource.IsFromMe = False
        mock_event.Info.Timestamp = 1234567890

        with patch(
            "agentic_framework.channels.whatsapp.Jid2String",
            side_effect=lambda x: "123456789@g.us" if "@g.us" in str(x) else str(x),
        ):
            whatsapp_channel._on_message_event(mock_client_class.return_value, mock_event)

        # Should ALWAYS be filtered (group chat)
        assert len(scheduled_coroutines) == 0, "Group chats must always be filtered"

    @pytest.mark.asyncio
    @patch("agentic_framework.channels.whatsapp.NewClient")
    @patch("asyncio.run_coroutine_threadsafe")
    async def test_lid_contact_when_allowed_contact_is_lid_format(
        self, mock_run_coro: MagicMock, mock_client_class: MagicMock, whatsapp_channel: WhatsAppChannel
    ) -> None:
        """Test that LID format works as allowed_contact.

        If user sets allowed_contact to a LID number, messages from that LID
        should work correctly. This is for scenarios where user's contact
        is stored as a LID by WhatsApp.
        """
        # User's allowed_contact is a LID number (no @lid domain)
        whatsapp_channel.allowed_contact = "118657162162293"

        scheduled_coroutines: list = []

        def capture_run_coro(coro, loop):
            scheduled_coroutines.append(coro)
            return MagicMock()

        mock_run_coro.side_effect = capture_run_coro

        async def mock_callback(msg):
            pass

        whatsapp_channel._message_callback = mock_callback
        whatsapp_channel._loop = MagicMock()

        # Message from LID that matches the allowed LID number
        mock_event = MagicMock()
        mock_event.Message.conversation = "Message from LID contact"
        mock_event.Info.MessageSource.Sender = "118657162162293@lid"
        mock_event.Info.MessageSource.Chat = "118657162162293@lid"
        mock_event.Info.MessageSource.IsFromMe = False
        mock_event.Info.Timestamp = 1234567890

        with patch("agentic_framework.channels.whatsapp.Jid2String", return_value="118657162162293@lid"):
            whatsapp_channel._on_message_event(mock_client_class.return_value, mock_event)

        # Should be processed (LID matches allowed_contact)
        assert len(scheduled_coroutines) == 1, "LID matching allowed LID should work"


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
