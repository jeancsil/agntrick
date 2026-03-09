"""Agntrick WhatsApp - WhatsApp integration for Agntrick agents.

This package provides WhatsApp communication capabilities for Agntrick agents,
including a WhatsApp channel implementation and specialized agents.

Example:
    >>> from agntrick_whatsapp import WhatsAppChannel, WhatsAppRouterAgent
    >>>
    >>> channel = WhatsAppChannel(
    ...     storage_path="~/storage/whatsapp",
    ...     allowed_contact="+1234567890"
    ... )
    >>> agent = WhatsAppRouterAgent(channel=channel)
    >>> await agent.start()
"""

from agntrick_whatsapp.channel import WhatsAppChannel
from agntrick_whatsapp.config import (
    AudioTranscriberConfig,
    ChannelConfig,
    FeatureFlags,
    LoggingConfig,
    PrivacyConfig,
    WhatsAppAgentConfig,
    WhatsAppBridgeConfig,
)
from agntrick_whatsapp.router import WhatsAppRouterAgent
from agntrick_whatsapp.transcriber import AudioTranscriber

__version__ = "0.2.0"

__all__ = [
    # Version
    "__version__",
    # Channel
    "WhatsAppChannel",
    # Agents
    "WhatsAppRouterAgent",
    # Config
    "AudioTranscriberConfig",
    "ChannelConfig",
    "FeatureFlags",
    "LoggingConfig",
    "PrivacyConfig",
    "WhatsAppAgentConfig",
    "WhatsAppBridgeConfig",
    # Services
    "AudioTranscriber",
]
