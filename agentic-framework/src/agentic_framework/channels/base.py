"""Base channel interface and message types for agent communication channels."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable


@dataclass
class IncomingMessage:
    """Incoming message from a communication channel.

    This represents a message received by the channel from a user,
    which will be processed by an agent.

    Attributes:
        text: The text content of the message.
        sender_id: The identifier of the message sender (phone number, user ID, etc.).
        channel_type: The type of channel (e.g., "whatsapp", "discord", "telegram").
        raw_data: The raw message data from the channel for advanced use.
        timestamp: When the message was received.
    """

    text: str
    sender_id: str
    channel_type: str
    raw_data: dict[str, Any]
    timestamp: float | datetime


@dataclass
class OutgoingMessage:
    """Outgoing message to be sent through a communication channel.

    This represents a message that an agent wants to send back to the user
    through the communication channel.

    Attributes:
        text: The text content of the message.
        recipient_id: The identifier of the recipient (phone number, user ID, etc.).
        media_url: Optional URL to media file to attach to the message.
        media_type: Optional type of media (e.g., "image", "video", "document", "audio").
    """

    text: str
    recipient_id: str
    media_url: str | None = None
    media_type: str | None = None


class Channel(ABC):
    """Abstract base class for communication channels.

    A Channel handles the bidirectional communication between users and agents.
    Implementations should handle the specific protocol of each platform
    (WhatsApp, Discord, Telegram, etc.) while providing a consistent interface.

    All channels must support:
    - Initialization and connection to the platform
    - Listening for incoming messages
    - Sending outgoing messages
    - Graceful shutdown

    Example implementations:
        - WhatsAppChannel: Uses WhatsApp for personal WhatsApp accounts
        - DiscordChannel: Uses discord.py for Discord
        - TelegramChannel: Uses python-telegram-bot for Telegram
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the channel connection.

        This method should:
        - Set up any required connections or sessions
        - Authenticate with the platform if needed
        - Prepare the channel to receive messages

        Raises:
            ChannelError: If initialization fails.
        """
        pass

    @abstractmethod
    async def listen(self, callback: Callable[[IncomingMessage], Any]) -> None:
        """Start listening for incoming messages.

        Args:
            callback: A callable that will be invoked with each IncomingMessage.
                       The callback should be async and will receive messages
                       as they arrive.

        This method should block until the channel is shutdown,
        processing messages in a loop and invoking the callback for each.
        The callback should handle any errors gracefully.

        Raises:
            ChannelError: If listening cannot be started.
        """
        pass

    @abstractmethod
    async def send(self, message: OutgoingMessage) -> None:
        """Send a message through the channel.

        Args:
            message: The OutgoingMessage to send.

        This method should handle both text and media messages.

        Raises:
            ChannelError: If the message cannot be sent.
            ValueError: If the message is invalid.
        """
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Gracefully shutdown the channel.

        This method should:
        - Stop listening for new messages
        - Close any open connections
        - Clean up resources

        Raises:
            ChannelError: If shutdown fails.
        """
        pass


class ChannelError(Exception):
    """Base exception for channel-related errors.

    All channel implementations should raise ChannelError or its subclasses
    for any errors that occur during channel operations.

    Attributes:
        message: Human-readable error description.
        channel_name: The name of the channel that raised the error.
    """

    def __init__(self, message: str, channel_name: str = "channel"):
        self.message = message
        self.channel_name = channel_name
        super().__init__(f"[{channel_name}] {message}")


class ConnectionError(ChannelError):
    """Raised when a channel fails to connect or authenticate."""


class MessageError(ChannelError):
    """Raised when a message cannot be sent or received."""


class ConfigurationError(ChannelError):
    """Raised when channel configuration is invalid."""
