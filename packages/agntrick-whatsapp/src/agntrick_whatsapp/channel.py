"""WhatsApp channel implementation using neonize library.

This module provides WhatsApp communication capabilities for agents using
the neonize library, which provides a Python API built on top of the
whatsmeow Go library for WhatsApp Web protocol.

The neonize library uses an event-driven architecture with a Go backend
for the actual WhatsApp Web protocol implementation.
"""

import asyncio
import contextlib
import hashlib
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable

try:
    from neonize.client import NewClient  # type: ignore
    from neonize.events import MessageEv  # type: ignore
    from neonize.utils import ChatPresence, ChatPresenceMedia  # type: ignore
    from neonize.utils.jid import Jid2String, build_jid  # type: ignore

    _NEONIZE_IMPORT_ERROR: Exception | None = None
except Exception as import_error:  # pragma: no cover - depends on system packages
    _NEONIZE_IMPORT_ERROR = import_error

    class NewClient:  # type: ignore[no-redef]
        """Fallback client that raises a clear error when neonize is unavailable."""

        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError(
                "neonize dependency is unavailable. Install system dependencies (e.g., libmagic) and neonize extras."
            ) from _NEONIZE_IMPORT_ERROR

    MessageEv = Any  # type: ignore[misc,assignment]

    class _ChatPresenceFallback:
        CHAT_PRESENCE_COMPOSING = "composing"
        CHAT_PRESENCE_PAUSED = "paused"

    class _ChatPresenceMediaFallback:
        CHAT_PRESENCE_MEDIA_TEXT = "text"

    ChatPresence = _ChatPresenceFallback  # type: ignore[assignment]
    ChatPresenceMedia = _ChatPresenceMediaFallback  # type: ignore[assignment]

    def Jid2String(value: Any) -> str:
        return str(value)

    def build_jid(phone: str, server: str = "s.whatsapp.net") -> str:
        return f"{phone}@{server}"


from agntrick_whatsapp.base import (
    Channel,
    ChannelError,
    ConfigurationError as ConfigError,
    IncomingMessage,
    OutgoingMessage,
)

# Alias for backward compatibility
ConfigurationError = ConfigError

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def _change_directory(path: Path):
    """Context manager for temporarily changing working directory.

    Ensures the original directory is restored even if an exception occurs.

    Args:
        path: The directory to change to.

    Yields:
        None
    """
    original_dir = Path.cwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(original_dir)


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
        typing_indicators: bool = True,
        min_typing_duration: float = 2.0,  # Minimum time (seconds) to show typing indicator
        dedup_window: float = 10.0,  # Time window (seconds) for duplicate detection
    ) -> None:
        self.storage_path = Path(storage_path).expanduser().resolve()
        self.allowed_contact = self._normalize_phone_number(allowed_contact)
        self.log_filtered_messages = log_filtered_messages
        self.typing_indicators = typing_indicators
        self._min_typing_duration = min_typing_duration
        self._dedup_window = dedup_window
        self._client: NewClient | None = None
        self._is_listening: bool = False
        self._message_callback: Callable[[IncomingMessage], Any] | None = None
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event = threading.Event()  # For signaling thread to stop
        self._original_dir = Path.cwd()  # Store original working directory
        self._typing_jids: set[str] = set()  # Track JIDs with active typing indicators
        self._typing_start_times: dict[str, float] = {}  # Track when typing started

        # Message deduplication using SQLite
        self._db_path = self.storage_path / "processed_messages.db"
        # Use thread-local storage for SQLite connections to avoid threading issues
        self._db_local = threading.local()
        self._db_lock = threading.Lock()  # Thread-safe DB operations

        # Validate storage path
        self._validate_storage_path()

        logger.info(
            f"WhatsAppChannel initialized with storage={self.storage_path}, allowed_contact={self.allowed_contact}, "
            f"typing_indicators={self.typing_indicators}, min_typing_duration={self._min_typing_duration}, "
            f"dedup_window={self._dedup_window}"
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

    def _send_typing(self, jid: str) -> None:
        """Send typing indicator to a JID.

        Args:
            jid: The JID to send typing indicator to.
        """
        if not self.typing_indicators or self._client is None:
            logger.debug(
                f"Skipping typing indicator for {jid}: "
                f"indicators={self.typing_indicators}, client={self._client is not None}"
            )
            return

        try:
            # Build JID object from string
            jid_obj = build_jid(jid)
            logger.info(f"Sending COMPOSING typing indicator to {jid}")
            # Send composing presence to show typing indicator
            self._client.send_chat_presence(
                jid_obj,
                ChatPresence.CHAT_PRESENCE_COMPOSING,
                ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT,
            )
            self._typing_jids.add(jid)
            self._typing_start_times[jid] = time.time()
            logger.info(f"Sent typing indicator to {jid} (active: {len(self._typing_jids)})")
        except Exception as e:
            logger.warning(f"Failed to send typing indicator: {e}")
            import traceback

            logger.warning(f"Typing error traceback: {traceback.format_exc()}")

    async def _stop_typing(self, jid: str) -> None:
        """Stop typing indicator for a JID.

        Args:
            jid: The JID to stop typing indicator for.
        """
        if not self.typing_indicators or self._client is None or jid not in self._typing_jids:
            logger.debug(f"Skipping stop typing for {jid}: in_jids={jid in self._typing_jids}")
            return

        # Enforce minimum typing duration
        if jid in self._typing_start_times:
            elapsed = time.time() - self._typing_start_times[jid]
            if elapsed < self._min_typing_duration:
                # Wait for minimum duration to pass
                wait_time = self._min_typing_duration - elapsed
                logger.info(
                    f"Waiting {wait_time:.1f}s before stopping typing indicator for {jid} (elapsed: {elapsed:.1f}s)"
                )
                await asyncio.sleep(wait_time)

        try:
            # Build JID object from string
            jid_obj = build_jid(jid)
            logger.info(f"Sending PAUSED typing indicator to {jid}")
            # Send paused presence to stop typing indicator
            self._client.send_chat_presence(
                jid_obj,
                ChatPresence.CHAT_PRESENCE_PAUSED,
                ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT,
            )
            self._typing_jids.discard(jid)
            self._typing_start_times.pop(jid, None)
            logger.info(f"Stopped typing indicator for {jid} (remaining active: {len(self._typing_jids)})")
        except Exception as e:
            logger.warning(f"Failed to stop typing indicator: {e}")
            import traceback

            logger.warning(f"Stop typing error traceback: {traceback.format_exc()}")

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

    def _get_db_connection(self) -> sqlite3.Connection:
        """Get or create a thread-local SQLite connection.

        Each thread gets its own connection to avoid SQLite threading issues.

        Returns:
            A SQLite connection for the current thread.
        """
        if not hasattr(self._db_local, "conn") or self._db_local.conn is None:
            self._db_local.conn = sqlite3.connect(str(self._db_path))
            # Initialize the table for this new connection
            cursor = self._db_local.conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processed_messages (
                    message_hash TEXT PRIMARY KEY,
                    sender_id TEXT NOT NULL,
                    first_seen_at REAL NOT NULL,
                    last_seen_at REAL NOT NULL
                )
            """)
            # Check if last_seen_at column exists, add if missing (schema migration)
            cursor.execute("PRAGMA table_info(processed_messages)")
            columns = [row[1] for row in cursor.fetchall()]
            if "last_seen_at" not in columns:
                # Old schema without last_seen_at, migrate by adding the column
                cursor.execute("ALTER TABLE processed_messages ADD COLUMN last_seen_at REAL NOT NULL DEFAULT 0")
                logger.info("Migrated database schema: added last_seen_at column")
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sender
                ON processed_messages(sender_id)
            """)
            self._db_local.conn.commit()
            logger.debug(f"Created thread-local DB connection for thread {threading.get_ident()}")
        return self._db_local.conn

    def _init_deduplication_db(self) -> None:
        """Initialize SQLite database for message deduplication.

        Creates a table to track message hashes and their first seen time.
        Uses SHA-256 hash of message content (not full text) to detect duplicates.

        Thread-local connections are used to avoid SQLite threading issues.
        """
        try:
            # Test by creating a connection in the current thread
            _ = self._get_db_connection()
            logger.info(f"Initialized deduplication DB: {self._db_path}")
            # Clean up old records on startup
            self._cleanup_old_deduplication_records()
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize deduplication DB: {e}")

    def _cleanup_old_deduplication_records(self, max_age_days: int = 90) -> None:
        """Clean up old deduplication records to prevent database bloat.

        Deletes records older than max_age_days to keep the database size manageable.
        This is called during initialization.

        Args:
            max_age_days: Maximum age of records to keep in days. Defaults to 90.
        """
        try:
            conn = self._get_db_connection()
            cutoff_time = time.time() - (max_age_days * 86400)  # days to seconds

            self._db_lock.acquire()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM processed_messages WHERE first_seen_at < ?",
                    (cutoff_time,),
                )
                deleted_count = cursor.rowcount
                conn.commit()

                if deleted_count > 0:
                    logger.info(
                        f"Cleaned up {deleted_count} old deduplication records (older than {max_age_days} days)"
                    )

            finally:
                self._db_lock.release()

        except sqlite3.Error as e:
            logger.error(f"Error cleaning up old deduplication records: {e}")

    def _is_duplicate_message(self, message_text: str, sender_id: str) -> bool:
        """Check if message is a duplicate using time-based deduplication.

        Messages from the same sender with identical content are considered duplicates
        only if they arrive within the deduplication window (default 10 seconds).
        After that time passes, the same message can be processed again.

        This allows legitimate repeated messages (like "Oi" sent multiple times)
        while still preventing true duplicate messages from spam.

        Args:
            message_text: The message content.
            sender_id: The sender's JID.

        Returns:
            True if message should be skipped, False otherwise.
        """
        try:
            conn = self._get_db_connection()
        except sqlite3.Error as e:
            # If DB not available, skip deduplication check
            # This allows agent to work if DB init fails
            logger.warning(f"Deduplication DB not available, skipping duplicate check: {e}")
            return False

        # Create hash of message content
        message_hash = hashlib.sha256(message_text.encode()).hexdigest()
        current_time = time.time()

        try:
            self._db_lock.acquire()
            try:
                cursor = conn.cursor()

                # Check if this exact message has been seen before
                cursor.execute(
                    "SELECT first_seen_at, last_seen_at FROM processed_messages WHERE message_hash = ?",
                    (message_hash,),
                )

                result = cursor.fetchone()

                if result is not None:
                    first_seen_at, last_seen_at = result
                    # Check if within dedup window from last time
                    time_since_last = current_time - last_seen_at
                    if time_since_last < self._dedup_window:
                        # Message was seen too recently - skip it
                        logger.debug(
                            f"Skipping duplicate message from {sender_id} "
                            f"(hash: {message_hash[:8]}..., {time_since_last:.1f}s ago)"
                        )
                        return True
                    else:
                        # Update last_seen_at since enough time has passed
                        cursor.execute(
                            "UPDATE processed_messages SET last_seen_at = ? WHERE message_hash = ?",
                            (current_time, message_hash),
                        )
                        conn.commit()
                        logger.debug(
                            f"Allowing message from {sender_id} (hash: {message_hash[:8]}..., "
                            f"{time_since_last:.1f}s ago, outside window)"
                        )
                        return False

                # First time seeing this message - store it
                cursor.execute(
                    "INSERT INTO processed_messages "
                    "(message_hash, sender_id, first_seen_at, last_seen_at) "
                    "VALUES (?, ?, ?, ?)",
                    (message_hash, sender_id, current_time, current_time),
                )
                conn.commit()
                logger.debug(f"First time seeing message from {sender_id} (hash: {message_hash[:8]}...)")
                return False

            finally:
                self._db_lock.release()

        except sqlite3.Error as e:
            logger.error(f"Error checking message deduplication: {e}")
            return False

    def _close_deduplication_db(self) -> None:
        """Close all SQLite database connections.

        Since we use thread-local connections, we close the connection
        from the current thread. Other threads' connections will be closed
        automatically when those threads terminate.

        Note: SQLite connections are automatically closed when the thread
        that created them terminates, but we explicitly close the
        current thread's connection for clean shutdown.
        """
        self._db_lock.acquire()
        try:
            if hasattr(self._db_local, "conn") and self._db_local.conn is not None:
                try:
                    self._db_local.conn.close()
                except sqlite3.Error as e:
                    logger.warning(f"Error closing DB connection: {e}")
                self._db_local.conn = None
                logger.info("Closed deduplication DB connection")
        finally:
            self._db_lock.release()

    def _restore_working_directory(self) -> None:
        """Restore process working directory to the original value."""
        try:
            os.chdir(self._original_dir)
            logger.debug(f"Restored working directory to: {self._original_dir}")
        except OSError as e:
            logger.error(f"Error restoring working directory: {e}")

    async def initialize(self) -> None:
        """Initialize the neonize client.

        This method creates the neonize client and permanently changes to the
        storage directory so that neonize persists session data in the correct
        location for the duration of the connection (including the background
        thread that calls connect()). The original directory is restored in
        shutdown().

        Raises:
            ChannelError: If neonize fails to initialize.
        """
        logger.info("Initializing neonize client...")

        # Initialize deduplication database for persistent duplicate prevention
        self._init_deduplication_db()

        cwd_changed = False
        try:
            # Permanently change to storage directory so neonize stores session
            # there.  We cannot use the _change_directory context manager here
            # because the background thread runs connect() *after* this method
            # returns, so we need CWD to remain changed until shutdown().
            os.chdir(self.storage_path)
            cwd_changed = True
            logger.debug(f"Changed working directory to: {self.storage_path}")

            # Create neonize sync client (will store session in current directory)
            self._client = NewClient("agentic-framework-whatsapp")

            # Set up event handler for incoming messages
            if self._client:
                self._client.event(MessageEv)(self._on_message_event)

            logger.info("Neonize client initialized successfully")

        except Exception as e:
            if cwd_changed:
                self._restore_working_directory()
            self._client = None
            raise ChannelError(
                f"Failed to initialize neonize client: {e}",
                channel_name="whatsapp",
            ) from e

    def _on_message_event(self, client: NewClient, event: MessageEv) -> None:
        """Handle incoming message events from neonize (sync callback).

        IMPORTANT: This is a synchronous callback invoked by the Go backend
        (neonize/whatsmeow). All async operations must be scheduled
        via `asyncio.run_coroutine_threadsafe()` to be executed on the
        main event loop.

        Args:
            client: The neonize client instance.
            event: The MessageEv from neonize.
        """
        if self._message_callback is None or self._loop is None:
            return

        try:
            # === STEP 1: Get sender info FIRST (before any message processing) ===
            sender_jid = Jid2String(event.Info.MessageSource.Sender)
            logger.debug(f"Received message from JID: {sender_jid}")

            # Also check chat JID (when messaging yourself, sender is LID but chat is phone number)
            chat_jid = Jid2String(event.Info.MessageSource.Chat) if event.Info.MessageSource.Chat else ""
            logger.debug(f"Chat JID: {chat_jid}")

            # Check SenderAlt and RecipientAlt for phone number
            sender_alt = ""
            if event.Info.MessageSource.SenderAlt:
                sender_alt = Jid2String(event.Info.MessageSource.SenderAlt)
                logger.debug(f"Sender Alt: {sender_alt}")

            recipient_alt = ""
            if event.Info.MessageSource.RecipientAlt:
                recipient_alt = Jid2String(event.Info.MessageSource.RecipientAlt)
                logger.debug(f"Recipient Alt: {recipient_alt}")

            # === STEP 2: SECURITY CHECKS FIRST ===
            # SECURITY: Reject group chats entirely to prevent privacy leaks
            # Group chats have JIDs ending with @g.us
            if chat_jid.endswith("@g.us"):
                if self.log_filtered_messages:
                    logger.info(f"Filtered group chat message from {chat_jid}")
                return

            # Check if message is from yourself (IsFromMe flag)
            is_from_me = event.Info.MessageSource.IsFromMe

            # Normalize phone numbers for comparison
            normalized_sender = self._normalize_phone_number(sender_jid)
            normalized_chat = self._normalize_phone_number(chat_jid) if chat_jid else ""
            normalized_sender_alt = self._normalize_phone_number(sender_alt) if sender_alt else ""
            normalized_recipient_alt = self._normalize_phone_number(recipient_alt) if recipient_alt else ""

            # SECURITY: Only allow messages from the explicitly allowed contact.
            # We check sender JID, chat JID, and alt fields to handle different messaging contexts.
            # For self-messages with LIDs, the phone number might be in SenderAlt or RecipientAlt.
            is_allowed = (
                normalized_sender == self.allowed_contact
                or normalized_chat == self.allowed_contact
                or normalized_sender_alt == self.allowed_contact
                or normalized_recipient_alt == self.allowed_contact
            )

            logger.debug(
                f"Normalized sender: {normalized_sender}, chat: {normalized_chat}, "
                f"allowed: {self.allowed_contact}, is_from_me: {is_from_me}, is_allowed: {is_allowed}"
            )

            if not is_allowed:
                if self.log_filtered_messages:
                    logger.info(f"Filtered message from {sender_jid}")
                return

            # === STEP 3: Extract message content ===
            message_text = getattr(event.Message, "conversation", "")
            if not message_text:
                extended_text = getattr(event.Message, "extendedTextMessage", None)
                if extended_text is not None:
                    message_text = getattr(extended_text, "text", "")

            # === STEP 4: Process message by type ===
            # If no text, check for audio message (voice notes, etc.)
            if not message_text:
                # Check for audio message - try different possible attribute names
                # neonize/whatsmeow may use different naming conventions
                audio_msg = None
                for attr_name in ["audioMessage", "AudioMessage", "audio_message", "ptt"]:
                    if hasattr(event.Message, attr_name):
                        audio_msg = getattr(event.Message, attr_name)
                        logger.debug(f"Found audio attribute: {attr_name}")
                        break

                if audio_msg is not None:
                    # Check if it has URL or other download attributes
                    # Note: neonize uses 'URL' (uppercase), not 'url' (lowercase)
                    audio_url = getattr(audio_msg, "URL", None) or getattr(audio_msg, "url", None)
                    if audio_url:
                        # This is a real audio message (voice note)
                        logger.debug("Detected audio message with URL - processing...")
                        asyncio.run_coroutine_threadsafe(
                            self._process_audio_and_callback(client, event),
                            self._loop,
                        )
                        return
                    else:
                        logger.warning("Audio message found but no 'URL' or 'url' attribute")
                else:
                    logger.debug("No audio message attribute found on event.Message")

                logger.debug("Skipping message without text or audio")
                return  # Skip messages without text or audio

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

            # Send typing indicator if enabled
            self._send_typing(reply_to_jid)

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
        self._loop = asyncio.get_running_loop()

        logger.info("Starting to listen for WhatsApp messages...")

        # Start neonize client in a separate thread to avoid blocking the event loop
        def _run_client() -> None:
            try:
                assert self._client is not None

                # Check if session file exists and its size
                # The session file name is based on device name, but device_props may be None
                # until after connect(). Use the default name "agentic-framework-whatsapp"
                session_file_name = "agentic-framework-whatsapp"
                if self._client.device_props is not None:
                    session_file_name = self._client.device_props.name

                session_file = self.storage_path / session_file_name
                if session_file.exists():
                    session_size = session_file.stat().st_size
                    session_age = time.time() - session_file.stat().st_mtime
                    age_hours = session_age / 3600
                    logger.info(
                        f"Found existing session file: {session_file.name} "
                        f"(size={session_size / 1024 / 1024:.1f}MB, age={age_hours:.1f}h)"
                    )
                else:
                    logger.warning("No existing session file found - QR code scan will be required")

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
                error_msg = str(e)
                logger.error(f"Error in neonize client thread: {error_msg}")

                # Provide helpful guidance based on error type
                if "401" in error_msg or "logged out" in error_msg.lower():
                    logger.error(
                        "WhatsApp session was rejected (401). This could mean:\n"
                        "  1. Session expired (WhatsApp sessions expire after ~14 days of inactivity)\n"
                        "  2. Another device logged out this session\n"
                        "  3. Password/2FA changed on WhatsApp account\n"
                        "  4. WhatsApp security policy changed\n\n"
                        "To fix: Delete the session file and scan QR code again.\n"
                        f"Session location: {self.storage_path}"
                    )
                elif "EOF" in error_msg:
                    logger.error(
                        "Connection closed unexpectedly (EOF). This could be:\n"
                        "  1. Network connectivity issue\n"
                        "  2. WhatsApp server unavailable\n"
                        "  3. Session was invalidated mid-connection\n"
                    )

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
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self._client.send_message, jid, message.text)

            logger.info("Message sent")

        except Exception as e:
            raise ChannelError(
                f"Failed to send message: {e}",
                channel_name="whatsapp",
            ) from e
        finally:
            # Stop typing indicator after sending (regardless of success/failure)
            await self._stop_typing(message.recipient_id)

    async def _send_media(self, jid: str, media_url: str, caption: str, media_type: str) -> None:
        """Send a media message.

        Args:
            jid: The JID to send to.
            media_url: URL to the media file.
            caption: Caption for the media.
            media_type: Type of media (image, video, document, audio). Used as fallback.
        """
        if self._client is None:
            raise ChannelError("Client not initialized. Call initialize() first.", channel_name="whatsapp")

        # Download media from URL
        import httpx

        async with httpx.AsyncClient() as http_client:
            response = await http_client.get(media_url)
            response.raise_for_status()
            media_data = response.content

        # Use Content-Type from response header for accurate mime type
        # Fallback to provided media_type if header is not available
        mime_type = response.headers.get("content-type", "image/jpeg")

        # Fallback mapping if content-type is not provided
        if "content-type" not in response.headers:
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

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _build_and_send)

    async def shutdown(self) -> None:
        """Gracefully shutdown the WhatsApp channel.

        This stops listening for messages and closes connections.
        """
        logger.info("Shutting down WhatsApp channel...")

        self._is_listening = False
        self._message_callback = None
        self._stop_event.set()  # Signal to client thread to stop

        # Clear typing indicators
        self._typing_jids.clear()

        # Close deduplication database
        self._close_deduplication_db()

        # Disconnect client and clear reference
        if self._client:
            try:
                # Disconnect the client
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self._client.disconnect)
            except Exception as e:
                logger.error(f"Error during disconnect: {e}")
            finally:
                self._client = None

        # Restore original working directory (was changed during initialization).
        self._restore_working_directory()

        # Wait for thread to finish, and warn if it outlives the timeout
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                logger.warning("Worker thread did not stop within timeout — possible resource leak")

        logger.info("WhatsApp channel shutdown complete")

    async def _process_audio_and_callback(self, client: NewClient, event: MessageEv) -> None:
        """Process audio message and invoke callback with result.

        Security checks (group filtering, allowed contact) are already done in _on_message_event
        before this method is called.

        Args:
            client: The neonize client instance.
            event: The MessageEv containing the audio message.
        """
        if self._message_callback is None:
            return

        try:
            # Get sender info for reply
            sender_jid = Jid2String(event.Info.MessageSource.Sender)
            chat_jid = Jid2String(event.Info.MessageSource.Chat) if event.Info.MessageSource.Chat else ""
            is_from_me = event.Info.MessageSource.IsFromMe

            # Process the audio message
            incoming = await self._process_audio_message(client, event)
            if incoming is None:
                logger.warning("Audio processing returned None")
                return

            # For self-messages, use chat_jid (phone number) as sender_id
            reply_to_jid = chat_jid if is_from_me and chat_jid else sender_jid
            # Update sender_id to correct JID for reply
            incoming.sender_id = reply_to_jid

            # Send typing indicator if enabled
            self._send_typing(reply_to_jid)

            # Invoke the callback
            await self._message_callback(incoming)

        except Exception as e:
            logger.error(f"Error processing audio message event: {e}")
            import traceback

            logger.error(f"Audio event processing traceback: {traceback.format_exc()}")

    async def _process_audio_message(self, client: NewClient, event: MessageEv) -> IncomingMessage | None:
        """Process an audio message by downloading and saving it for transcription.

        Args:
            client: The neonize client instance.
            event: The MessageEv containing the audio message.

        Returns:
            IncomingMessage with audio metadata for transcription, or None if processing fails.

        Note:
            whatsmeow handles decryption automatically. The download methods return
            decrypted audio data. Transcription is handled by WhatsAppAgent,
            not here (see whatsapp_agent.py lines 327-350).
        """
        import tempfile

        # Get sender info
        sender_jid = Jid2String(event.Info.MessageSource.Sender)
        logger.info(f"Processing audio message from {sender_jid}")

        try:
            audio_msg = event.Message.audioMessage

            # Download audio data using neonize client
            # Note: This runs in a thread pool to avoid blocking
            loop = asyncio.get_running_loop()

            def _download_audio() -> tuple[bytes, str, str]:
                assert client is not None
                # Use neonize's download_any which handles decryption automatically
                # download_any takes the Message object and returns decrypted bytes
                if hasattr(client, "download_any"):
                    audio_data = client.download_any(event.Message)
                    if audio_data:
                        return (
                            audio_data,
                            getattr(audio_msg, "mimetype", "audio/ogg"),
                            str(getattr(audio_msg, "seconds", 0)),
                        )

                # Fallback error if download_any not available
                raise ValueError(
                    "Audio download failed: neonize client does not have download_any method. "
                    "Encrypted media cannot be decrypted without proper download method."
                )

            audio_data, mime_type, duration = await loop.run_in_executor(None, _download_audio)
            logger.info(f"Downloaded {len(audio_data)} bytes of audio data")

            # Determine file extension from mime type
            # WhatsApp voice messages are typically OGG/OPUS format
            mime_to_ext = {
                "audio/mpeg": ".mp3",
                "audio/mp3": ".mp3",
                "audio/wav": ".wav",
                "audio/wave": ".wav",
                "audio/ogg": ".ogg",
                "audio/opus": ".ogg",
                "audio/x-opus": ".ogg",
                "audio/aac": ".m4a",
                "audio/mp4": ".m4a",
                "audio/webm": ".webm",
            }
            ext = mime_to_ext.get(mime_type, ".ogg")  # Default to .ogg for WhatsApp voice

            # Save audio to temporary file for transcription
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_file:
                tmp_file.write(audio_data)
                audio_path = tmp_file.name
            logger.info(f"Saved audio to temporary file: {audio_path}")

            # Return IncomingMessage with audio metadata for WhatsAppAgent to transcribe
            # Note: Transcription happens in WhatsAppAgent, not here
            return IncomingMessage(
                text="[Audio message received]",  # Placeholder, agent will transcribe
                sender_id=sender_jid,
                channel_type="whatsapp",
                raw_data={
                    "event": event,
                    "is_audio": True,
                    "audio_path": audio_path,
                    "audio_mime_type": mime_type,
                    "audio_duration": duration,
                },
                timestamp=getattr(event.Info, "Timestamp", 0),
            )

        except Exception as e:
            logger.error(f"Error processing audio message: {e}")
            import traceback

            logger.error(f"Audio processing traceback: {traceback.format_exc()}")
            # Return error message as IncomingMessage
            return IncomingMessage(
                text=f"[Audio download error: {str(e)}]",
                sender_id=sender_jid,
                channel_type="whatsapp",
                raw_data={"event": event},
                timestamp=getattr(event.Info, "Timestamp", 0),
            )
