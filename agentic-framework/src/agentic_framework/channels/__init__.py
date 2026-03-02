"""Communication channels for agents (WhatsApp, Discord, Telegram, etc.)."""

from agentic_framework.channels.base import (
    Channel,
    ChannelError,
    ConfigurationError,
    ConnectionError,
    IncomingMessage,
    MessageError,
    OutgoingMessage,
)
from agentic_framework.channels.whatsapp import WhatsAppChannel
from agentic_framework.channels.whatsapp_config import WhatsAppAgentConfig

__all__ = [
    "Channel",
    "IncomingMessage",
    "OutgoingMessage",
    "ChannelError",
    "ConnectionError",
    "MessageError",
    "ConfigurationError",
    "WhatsAppChannel",
    "WhatsAppAgentConfig",
]
