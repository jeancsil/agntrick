"""WhatsApp channel implementation using neonize library.

This module provides WhatsApp communication capabilities for agents using
the neonize library, which provides a Python API built on top of the
whatsmeow Go library for WhatsApp Web protocol.

The neonize library uses an event-driven architecture with a Go backend
for the actual WhatsApp Web protocol implementation.
"""

import asyncio
import hashlib
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable

from neonize.client import NewClient  # type: ignore
from neonize.events import MessageEv  # type: ignore
from neonize.utils.jid import Jid2String, build_jid  # type: ignore

from agentic_framework.channels.base import (
    Channel,
    ChannelError,
    ConfigurationError,
    IncomingMessage,
    OutgoingMessage,
)

logger = logging.getLogger(__name__)


class WhatsAppChannel(Channel):
    """WhatsApp communication channel using neonize.

    This channel provides bidirectional communication with WhatsApp using
    a personal WhatsApp account. It handles:
    - QR code-based authentication
    - Text and media messages
    - Contact filtering for privacy
    - Local storage for session data

    Args:
        storage_path: Directory where neonize will store data
                      (sessions, media, database).
        allowed_contact: Phone number to allow messages from (e.g., "+34 666 666 666").
                         Messages from other numbers are ignored.
        log_filtered_messages: If True, log filtered messages without processing.
        poll_interval: Seconds between message polling checks (not used in event-driven mode).

    Raises:
        ConfigurationError: If storage_path is invalid.
    """

    def __init__(
        self,
        storage_path: str | Path,
        allowed_contact: str,
        log_filtered_messages: bool = False,
        poll_interval: float = 1.0,  # Kept for API compatibility, not used in event mode
    ) -> None:
        self.storage_path = Path(storage_path).expanduser().resolve()
        self.allowed_contact = self._normalize_phone_number(allowed_contact)
        self.log_filtered_messages = log_filtered_messages
        self._client: NewClient | None = None
        self._is_listening: bool = False
        self._message_callback: Callable[[IncomingMessage], Any] | None = None
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event = threading.Event()  # For signaling thread to stop
        self._original_dir = Path.cwd()  # Store original working directory

        # Message deduplication using SQLite
        self._db_path = self.storage_path / "processed_messages.db"
        self._db: sqlite3.Connection | None = None
        self._db_lock = threading.Lock()  # Thread-safe DB access

        # Validate storage path
        self._validate_storage_path()

        logger.info(
            f"WhatsAppChannel initialized with storage={self.storage_path}, allowed_contact={self.allowed_contact}"
        )

    @staticmethod
    def _normalize_phone_number(phone: str) -> str:
        """Normalize a phone number to a consistent format.

        Args:
            phone: Phone number in any format or JID (e.g., "1234567890@s.whatsapp.net").

        Returns:
            Normalized phone number with spaces, special chars, and JID domain removed.
        """
        # Remove JID domain if present (e.g., "1234567890@s.whatsapp.net" -> "1234567890")
        if "@" in phone:
            phone = phone.split("@")[0]

        # Remove all non-digit characters (except + at start)
        cleaned = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        # Remove + if present (whatsapp expects format without +)
        return cleaned.lstrip("+")

    def _validate_storage_path(self) -> None:
        """Validate that storage_path is a writable directory.

        Raises:
            ConfigurationError: If storage_path is invalid or not writable.
        """
        try:
            self.storage_path.mkdir(parents=True, exist_ok=True)
            # Test writability
            test_file = self.storage_path / ".write_test"
            test_file.touch()
            test_file.unlink()
        except (OSError, IOError) as e:
            raise ConfigurationError(
                f"Cannot write to storage path '{self.storage_path}': {e}",
                channel_name="whatsapp",
            ) from e

    def _init_deduplication_db(self) -> None:
        """Initialize SQLite database for message deduplication.

        Creates a table to track message hashes and their first seen time.
        Uses SHA-256 hash of message content (not full text) to detect duplicates.

        TODO: Consider adding cleanup for old records (e.g., delete records older than 90 days)
              to prevent database from growing indefinitely.
        """
        try:
            self._db = sqlite3.connect(str(self._db_path))
            self._db_lock.acquire()
            try:
                cursor = self._db.cursor()

                # Create table if not exists
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS processed_messages (
                        message_hash TEXT PRIMARY KEY,
                        sender_id TEXT NOT NULL,
                        first_seen_at REAL NOT NULL
                    )
                """)

                # Create index for faster lookups
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_sender
                    ON processed_messages(sender_id)
                """)

                self._db.commit()
                logger.info(f"Initialized deduplication DB: {self._db_path}")

            finally:
                self._db_lock.release()

        except sqlite3.Error as e:
            logger.error(f"Failed to initialize deduplication DB: {e}")

    def _is_duplicate_message(self, message_text: str, sender_id: str) -> bool:
        """Check if message is a duplicate using SQLite.

        Args:
            message_text: The message content.
            sender_id: The sender's JID.

        Returns:
            True if message should be skipped, False otherwise.
        """
        if self._db is None:
            # If DB not initialized, skip deduplication check
            # This allows agent to work if DB init fails
            logger.warning("Deduplication DB not available, skipping duplicate check")
            return False

        # Create hash of message content
        message_hash = hashlib.sha256(message_text.encode()).hexdigest()

        try:
            self._db_lock.acquire()
            try:
                cursor = self._db.cursor()

                # Check if this exact message has been seen before
                cursor.execute("SELECT sender_id FROM processed_messages WHERE message_hash = ?", (message_hash,))

                result = cursor.fetchone()

                if result is not None:
                    # Message was seen before - skip it
                    logger.debug(f"Skipping duplicate message from {sender_id} (hash: {message_hash[:8]}...)")
                    return True

                # First time seeing this message - store it
                cursor.execute(
                    "INSERT INTO processed_messages (message_hash, sender_id, first_seen_at) VALUES (?, ?, ?)",
                    (message_hash, sender_id, time.time()),
                )
                self._db.commit()
                return False

            finally:
                self._db_lock.release()

        except sqlite3.Error as e:
            logger.error(f"Error checking message deduplication: {e}")
            return False

    def _close_deduplication_db(self) -> None:
        """Close SQLite database connection."""
        if self._db is not None:
            self._db_lock.acquire()
            try:
                self._db.close()
                self._db = None
                logger.info("Closed deduplication DB")
            finally:
                self._db_lock.release()

    async def initialize(self) -> None:
        """Initialize the neonize client.

        This method creates the neonize client and changes to the storage
        directory to ensure session data is persisted in the correct location.

        Raises:
            ChannelError: If neonize fails to initialize.
        """
        logger.info("Initializing neonize client...")

        # Initialize deduplication database for persistent duplicate prevention
        self._init_deduplication_db()

        try:
            # Change to storage directory so neonize stores session there
            # The database is created when connect() is called, so we need
            # to stay in this directory for the duration of the connection
            os.chdir(self.storage_path)
            logger.debug(f"Changed working directory to: {self.storage_path}")

            # Create neonize sync client (will store session in current directory)
            self._client = NewClient("agentic-framework-whatsapp")

            # Set up event handler for incoming messages
            if self._client:
                self._client.event(MessageEv)(self._on_message_event)

            logger.info("Neonize client initialized successfully")

        except Exception as e:
            # Restore original directory on error
            os.chdir(self._original_dir)
            raise ChannelError(
                f"Failed to initialize neonize client: {e}",
                channel_name="whatsapp",
            ) from e

    def _on_message_event(self, client: NewClient, event: MessageEv) -> None:
        """Handle incoming message events from neonize (sync callback).

        Args:
            client: The neonize client instance.
            event: The MessageEv from neonize.
        """
        if self._message_callback is None or self._loop is None:
            return

        try:
            # Extract message data
            message_text = getattr(event.Message, "conversation", "")
            if not message_text and hasattr(event.Message, "extended_text_message"):
                message_text = event.Message.extended_text_message.text

            if not message_text:
                logger.debug("Skipping message without text")
                return  # Skip messages without text

            # Get sender info - use Jid2String to get proper string representation
            sender_jid = Jid2String(event.Info.MessageSource.Sender)
            logger.debug(f"Received message from JID: {sender_jid}")

            # Also check chat JID (when messaging yourself, sender is LID but chat is phone number)
            chat_jid = Jid2String(event.Info.MessageSource.Chat) if event.Info.MessageSource.Chat else ""
            logger.debug(f"Chat JID: {chat_jid}")

            # Check if message is from yourself (IsFromMe flag)
            is_from_me = event.Info.MessageSource.IsFromMe

            # Normalize phone numbers for comparison
            normalized_sender = self._normalize_phone_number(sender_jid)
            normalized_chat = self._normalize_phone_number(chat_jid) if chat_jid else ""

            # Check if message is from allowed contact
            # For regular messages: compare phone number
            # For self-messages: allow if IsFromMe is true (messaging yourself from same device)
            is_allowed = (
                is_from_me or normalized_sender == self.allowed_contact or normalized_chat == self.allowed_contact
            )

            logger.debug(
                f"Normalized sender: {normalized_sender}, chat: {normalized_chat}, "
                f"allowed: {self.allowed_contact}, is_from_me: {is_from_me}, is_allowed: {is_allowed}"
            )

            if not is_allowed:
                if self.log_filtered_messages:
                    logger.info(f"Filtered message from {sender_jid}")
                return

            # Message deduplication using SQLite: skip if message hash exists
            if self._is_duplicate_message(message_text, sender_jid):
                return

            # Create incoming message - for self-messages, use chat_jid (phone number) as sender_id
            # so responses are sent to correct JID
            reply_to_jid = chat_jid if is_from_me and chat_jid else sender_jid
            incoming = IncomingMessage(
                text=message_text,
                sender_id=reply_to_jid,
                channel_type="whatsapp",
                raw_data={"event": event},
                timestamp=getattr(event.Info, "Timestamp", 0),
            )

            # Schedule callback on the main event loop
            async def _invoke_callback() -> None:
                if self._message_callback is not None:
                    await self._message_callback(incoming)

            asyncio.run_coroutine_threadsafe(_invoke_callback(), self._loop)

        except Exception as e:
            logger.error(f"Error processing message event: {e}")

    async def listen(self, callback: Callable[[IncomingMessage], Any]) -> None:
        """Start listening for incoming WhatsApp messages.

        This method starts the event loop for receiving messages from neonize.
        The callback will be invoked for each message from the allowed contact.

        Args:
            callback: Async callable to invoke with each incoming message.

        Raises:
            ChannelError: If listening cannot be started.
        """
        if self._client is None:
            raise ChannelError(
                "Channel not initialized. Call initialize() first.",
                channel_name="whatsapp",
            )

        if self._is_listening:
            logger.warning("Already listening for messages")
            return

        self._is_listening = True
        self._message_callback = callback
        self._loop = asyncio.get_event_loop()

        logger.info("Starting to listen for WhatsApp messages...")

        # Start neonize client in a separate thread to avoid blocking the event loop
        def _run_client() -> None:
            try:
                assert self._client is not None
                # Connect to WhatsApp (may require QR code scan on first run)
                logger.info("Connecting to WhatsApp (scan QR code if prompted)...")
                self._client.connect()
                logger.info("WhatsApp client connected")

                # Wait for stop signal
                logger.info("Waiting for messages...")
                while not self._stop_event.is_set():
                    # Small sleep to avoid busy-waiting
                    self._stop_event.wait(timeout=0.1)

            except Exception as e:
                logger.error(f"Error in neonize client thread: {e}")

        self._thread = threading.Thread(target=_run_client, daemon=True)
        self._thread.start()

        # Wait for stop signal
        try:
            while self._is_listening and (self._thread is None or self._thread.is_alive()):
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Listening cancelled")

    async def send(self, message: OutgoingMessage) -> None:
        """Send a message through WhatsApp.

        Args:
            message: The OutgoingMessage to send.

        Raises:
            MessageError: If the message cannot be sent.
            ChannelError: If the channel is not initialized.
        """
        if self._client is None:
            raise ChannelError(
                "Channel not initialized. Call initialize() first.",
                channel_name="whatsapp",
            )

        try:
            # For LID contacts (@lid), build JID with lid server
            if "@lid" in message.recipient_id:
                phone = self._normalize_phone_number(message.recipient_id)
                jid = build_jid(phone, server="lid")
            else:
                # For regular JIDs or phone numbers, use build_jid (default s.whatsapp.net)
                phone_number = self._normalize_phone_number(message.recipient_id)
                jid = build_jid(phone_number)

            if message.media_url:
                # Send media message
                media_type = message.media_type or "image"
                await self._send_media(jid, message.media_url, message.text, media_type)
            else:
                # Send text message - run in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._client.send_message, jid, message.text)

            logger.info("Message sent")

        except Exception as e:
            raise ChannelError(
                f"Failed to send message: {e}",
                channel_name="whatsapp",
            ) from e

    async def _send_media(self, jid: str, media_url: str, caption: str, media_type: str) -> None:
        """Send a media message.

        Args:
            jid: The JID to send to.
            media_url: URL to the media file.
            caption: Caption for the media.
            media_type: Type of media (image, video, document, audio).
        """
        if self._client is None:
            raise RuntimeError("Client not initialized")

        # Download media from URL
        import httpx

        async with httpx.AsyncClient() as http_client:
            response = await http_client.get(media_url)
            response.raise_for_status()
            media_data = response.content

        # Determine mime type
        mime_types = {
            "image": "image/jpeg",
            "video": "video/mp4",
            "document": "application/pdf",
            "audio": "audio/mpeg",
        }
        mime_type = mime_types.get(media_type, "image/jpeg")

        # Build and send media message based on type - run in thread pool
        def _build_and_send() -> None:
            assert self._client is not None
            if media_type == "image":
                msg = self._client.build_image_message(media_data, caption=caption, mime_type=mime_type)
            elif media_type == "video":
                msg = self._client.build_video_message(media_data, caption=caption, mime_type=mime_type)
            elif media_type == "document":
                filename = media_url.split("/")[-1]
                msg = self._client.build_document_message(
                    media_data, filename=filename, caption=caption, mime_type=mime_type
                )
            elif media_type == "audio":
                msg = self._client.build_audio_message(media_data, mime_type=mime_type)
            else:
                # Default to image
                msg = self._client.build_image_message(media_data, caption=caption, mime_type=mime_type)
            self._client.send_message(jid, message=msg)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _build_and_send)

    async def shutdown(self) -> None:
        """Gracefully shutdown the WhatsApp channel.

        This stops listening for messages and closes connections.
        """
        logger.info("Shutting down WhatsApp channel...")

        self._is_listening = False
        self._message_callback = None
        self._stop_event.set()  # Signal to client thread to stop

        # Close deduplication database
        self._close_deduplication_db()

        if self._client:
            try:
                # Disconnect the client
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._client.disconnect)
            except Exception as e:
                logger.error(f"Error during disconnect: {e}")
            finally:
                self._client = None

        # Restore original working directory
        try:
            os.chdir(self._original_dir)
            logger.debug(f"Restored working directory to: {self._original_dir}")
        except Exception as e:
            logger.error(f"Error restoring working directory: {e}")

        # Wait for thread to finish
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

        logger.info("WhatsApp channel shutdown complete")
