"""Tests for the base Channel interface and message types."""

import time
from datetime import datetime

import pytest

from agentic_framework.channels.base import (
    Channel,
    ChannelError,
    ConfigurationError,
    ConnectionError,
    IncomingMessage,
    MessageError,
    OutgoingMessage,
)


class TestIncomingMessage:
    """Tests for IncomingMessage dataclass."""

    def test_create_with_timestamp_float(self) -> None:
        """Test creating IncomingMessage with float timestamp."""
        msg = IncomingMessage(
            text="Hello",
            sender_id="user123",
            channel_type="test",
            raw_data={},
            timestamp=123456.0,
        )
        assert msg.text == "Hello"
        assert msg.sender_id == "user123"
        assert msg.channel_type == "test"
        assert msg.timestamp == 123456.0

    def test_create_with_timestamp_datetime(self) -> None:
        """Test creating IncomingMessage with datetime timestamp."""
        now = datetime.now()
        msg = IncomingMessage(
            text="Hello",
            sender_id="user123",
            channel_type="test",
            raw_data={},
            timestamp=now,
        )
        assert msg.text == "Hello"
        assert msg.sender_id == "user123"
        assert msg.channel_type == "test"
        assert msg.timestamp == now


class TestOutgoingMessage:
    """Tests for OutgoingMessage dataclass."""

    def test_create_text_only(self) -> None:
        """Test creating OutgoingMessage with text only."""
        msg = OutgoingMessage(
            text="Response",
            recipient_id="user123",
        )
        assert msg.text == "Response"
        assert msg.recipient_id == "user123"
        assert msg.media_url is None
        assert msg.media_type is None

    def test_create_with_media(self) -> None:
        """Test creating OutgoingMessage with media."""
        msg = OutgoingMessage(
            text="Here is the image",
            recipient_id="user123",
            media_url="https://example.com/image.jpg",
            media_type="image",
        )
        assert msg.text == "Here is the image"
        assert msg.recipient_id == "user123"
        assert msg.media_url == "https://example.com/image.jpg"
        assert msg.media_type == "image"


class MockChannel(Channel):
    """Mock implementation of Channel for testing."""

    def __init__(self) -> None:
        self.initialized = False
        self.sent_messages: list[OutgoingMessage] = []
        self.listening = False

    async def initialize(self) -> None:
        self.initialized = True

    async def listen(self, callback: callable) -> None:  # type: ignore[override]
        self.listening = True
        # Simulate one message then stop
        await callback(
            IncomingMessage(
                text="Test message",
                sender_id="test_user",
                channel_type="mock",
                raw_data={},
                timestamp=time.time(),
            )
        )
        self.listening = False

    async def send(self, message: OutgoingMessage) -> None:
        self.sent_messages.append(message)

    async def shutdown(self) -> None:
        self.initialized = False
        self.listening = False


class TestChannel:
    """Tests for the Channel abstract base class."""

    def test_cannot_instantiate_abstract_channel(self) -> None:
        """Test that Channel cannot be instantiated directly."""
        with pytest.raises(TypeError):
            Channel()  # type: ignore[abstract]


class TestMockChannel:
    """Tests for the mock channel implementation."""

    @pytest.mark.asyncio
    async def test_initialize(self) -> None:
        """Test that mock channel initializes correctly."""
        channel = MockChannel()
        assert not channel.initialized
        await channel.initialize()
        assert channel.initialized

    @pytest.mark.asyncio
    async def test_send_message(self) -> None:
        """Test that mock channel sends messages correctly."""
        channel = MockChannel()
        await channel.initialize()

        msg = OutgoingMessage(
            text="Test response",
            recipient_id="user123",
        )
        await channel.send(msg)

        assert len(channel.sent_messages) == 1
        assert channel.sent_messages[0].text == "Test response"
        assert channel.sent_messages[0].recipient_id == "user123"

    @pytest.mark.asyncio
    async def test_listen_and_callback(self) -> None:
        """Test that mock channel calls callback with messages."""
        channel = MockChannel()
        await channel.initialize()

        received_messages: list[IncomingMessage] = []

        async def callback(msg: IncomingMessage) -> None:
            received_messages.append(msg)

        await channel.listen(callback)

        assert len(received_messages) == 1
        assert received_messages[0].text == "Test message"
        assert received_messages[0].sender_id == "test_user"

    @pytest.mark.asyncio
    async def test_shutdown(self) -> None:
        """Test that mock channel shuts down correctly."""
        channel = MockChannel()
        await channel.initialize()
        assert channel.initialized

        await channel.shutdown()
        assert not channel.initialized


class TestChannelExceptions:
    """Tests for Channel exception classes."""

    def test_channel_error(self) -> None:
        """Test ChannelError base exception."""
        error = ChannelError("Test error", channel_name="test")
        assert str(error) == "[test] Test error"
        assert error.message == "Test error"
        assert error.channel_name == "test"

    def test_connection_error(self) -> None:
        """Test ConnectionError exception."""
        error = ConnectionError("Failed to connect", channel_name="whatsapp")
        assert isinstance(error, ChannelError)
        assert str(error) == "[whatsapp] Failed to connect"

    def test_message_error(self) -> None:
        """Test MessageError exception."""
        error = MessageError("Failed to send", channel_name="telegram")
        assert isinstance(error, ChannelError)
        assert str(error) == "[telegram] Failed to send"

    def test_configuration_error(self) -> None:
        """Test ConfigurationError exception."""
        error = ConfigurationError("Invalid config", channel_name="discord")
        assert isinstance(error, ChannelError)
        assert str(error) == "[discord] Invalid config"
