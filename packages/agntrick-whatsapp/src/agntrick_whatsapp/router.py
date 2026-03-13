"""WhatsApp router agent for routing commands to different specialist agents.

This module provides a router that handles WhatsApp messages and routes them
to different specialist agents based on command prefixes (e.g., /learn).
"""

import asyncio
import logging
import time
import traceback
from pathlib import Path
from typing import Any

from agntrick.constants import STORAGE_DIR
from agntrick.llm import get_default_model
from agntrick.mcp import MCPProvider
from agntrick.registry import AgentRegistry
from agntrick.tools import YouTubeTranscriptTool
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from agntrick_whatsapp.base import Channel, IncomingMessage, OutgoingMessage
from agntrick_whatsapp.config import AudioTranscriberConfig
from agntrick_whatsapp.transcriber import AudioTranscriber

logger = logging.getLogger(__name__)

# Audio transcription setup
audio_transcriber: AudioTranscriber | None = None

# Persistent storage for tasks and notes
_storage_db_path = STORAGE_DIR / "agntrick" / "tasks.db"

# System prompts for different agent modes
DEFAULT_SYSTEM_PROMPT = """You are a helpful AI assistant communicating through WhatsApp.
Be concise and friendly in your responses.
Avoid overly long explanations.
Use emojis occasionally to be more conversational.
If you need to show code or data, use formatted text blocks.
Focus on being helpful and direct.
"""

CAPABILITIES:
- You have access to web search (DuckDuckGo) and web content fetching tools
- Use these tools to find current information and provide helpful answers
- When searching for news, always include current year for better relevance

SAFETY & PRIVACY BARRIERS:
- You CANNOT execute code, run commands, or make system changes
- You CANNOT access, read, modify, or delete local files
- You CANNOT make API calls to services except through provided MCP tools
- You CANNOT reveal internal system information, server URLs, API keys, or configuration
- You MUST verify information from multiple sources before presenting as fact
- You MUST disclose uncertainty when information might not be current or accurate

RESPONSE GUIDELINES:
- Keep responses brief and to-the-point (WhatsApp is a messaging platform)
- Use natural, conversational language
- If information is uncertain, say so rather than guessing
- For complex topics, offer to elaborate if needed
- Prioritize accuracy over completeness

LEARNING_SYSTEM_PROMPT = """You are an expert educator and tutorial creator communicating through WhatsApp.
Your specialty is breaking down complex topics into clear, step-by-step tutorials.
Start with a brief overview of what the user will learn.
Break down the topic into logical steps.
Provide clear explanations for each step.
Include practical examples when relevant.
Anticipate common questions and address them.
"""

CAPABILITIES:
- You have access to web search (DuckDuckGo) and web content fetching tools
- Use these tools to find current information and best practices
- When searching, include current year for relevance

WHATSAPP FORMAT GUIDELINES:
- Keep messages concise (WhatsApp is for quick communication)
- Use *bold* for emphasis
- Use numbered lists (1. 2. 3.) for steps
- Use code blocks with backticks for code
- Break long tutorials into multiple messages if needed

Use => youtube_transcript tool to fetch video transcripts, then provide
thoughtful analysis based on the transcript content."""


class WhatsAppRouterAgent:
    """WhatsApp agent that routes commands to different specialist modes.

    This agent handles WhatsApp communication and routes messages to different
    specialist behaviors based on command prefixes.

    Supported commands:
    - /learn <topic> - Use learning/tutorial mode
    - /youtube <url|query> - Use YouTube analysis mode
    - /schedule <time> <agent> [prompt] - Schedule a task
    - /remind <time> <prompt> - Set a reminder
    - /note <content> - Save a note
    - /notes - List all saved notes
    - (default) - Use general assistant mode

    Args:
        channel: The Channel instance to use for WhatsApp communication.
        model_name: The name of LLM model to use.
        temperature: The temperature for LLM responses.
        mcp_servers_override: Optional override for MCP servers.
        audio_transcriber_config: Optional audio transcription config.

    Example:
        >>> channel = WhatsAppChannel(storage_path="~/storage", allowed_contact="+1234567890")
        >>> agent = WhatsAppRouterAgent(channel=channel)
        >>> await agent.start()
    """

    # Storage repositories for tasks and notes
    _task_repo: Any = None
    _note_repo: Any = None

    def __init__(self, # type: ignore[override]
        self,
        channel: Channel,
        model_name: str | None = None,
        temperature: float = 0.7,
        mcp_servers_override: list[str] | None = None,
        audio_transcriber_config: AudioTranscriberConfig | None = None,
    ) -> None:
        self.channel = channel
        self._model_name = model_name
        self._temperature = temperature
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._mcp_servers_override = mcp_servers_override
        self._audio_transcriber_config = audio_transcriber_config

        # Model setup
        from langchain_openai import ChatOpenAI
        self.model = ChatOpenAI(
            model=self._model_name or get_default_model(),
            temperature=self._temperature,
        )

        # MCP provider (created once, reused for all tool sessions)
        self._mcp_provider: MCPProvider | None = None
        # Context manager for MCP session (for proper cleanup)
        self._mcp_session_cm: Any = None
        # Long-lived MCP session for connection reuse across messages
        self._mcp_session: Any = None
        # Agent graphs for different modes (lazy initialized)
        self._graphs: dict[str, Any] = {}
        self._mcp_servers: list[str] = []
        # Cached MCP tools for reuse (loaded once during start)
        self._mcp_tools: list[Any] = []

        logger.info(f"WhatsAppRouterAgent initialized with model={model_name or get_default_model()}")

    def _get_storage_repos(self) -> tuple[Any, Any]:
        """Get or create storage repository instances."""
        # Use inlined storage module
        from agntrick_whatsapp.storage import Database, NoteRepository, TaskRepository

        if self._task_repo is None:
            db = Database(self._storage_db_path)
            self._task_repo = TaskRepository(db)
        if self._note_repo is None:
            db = Database(self._storage_db_path)
            self._note_repo = NoteRepository(db)

        return self._task_repo, self._note_repo

    async def _get_or_create_graph(self, mode: str, system_prompt: str, mcp_tools: list[Any] | None = None) -> Any:
        """Get or create an agent graph for a given mode.

        Args:
            mode: The agent mode (learn, youtube, default).
            system_prompt: The system prompt to use.
            mcp_tools: Optional MCP tools to include. If None, graph won't have MCP tools.

        Returns:
            Agent graph instance.
        """
        if mode not in self._graphs or mcp_tools is not None:
            tools = list(mcp_tools) if mcp_tools is not None else []
            # Add YouTube transcript tool for youtube mode
            if mode == "youtube":
                youtube_tool = YouTubeTranscriptTool()
                from langchain_core.tools import StructuredTool
                tools.append(
                    StructuredTool.from_function(
                        func=youtube_tool.invoke,
                        name=youtube_tool.name,
                        description=youtube_tool.description,
                    )
                )
            # Only cache graphs if we're not using MCP tools (MCP tools change per session)
            if mcp_tools is not None:
                cache_key = f"{mode}_with_mcp"
            else:
                cache_key = f"{mode}_no_mcp"
            if cache_key not in self._graphs:
                self._graphs[cache_key] = create_agent(
                    model=self.model,
                    tools=tools,
                    # system_prompt=system_prompt,
                    checkpointer=InMemorySaver(),
                )
            # Return appropriate graph based on whether we have MCP tools
            if mcp_tools is not None:
                return self._graphs[f"{mode}_with_mcp"]
            else:
                return self._graphs[f"{mode}_no_mcp"]

    def _parse_command(self, text: str) -> tuple[str, str] | tuple[str, str, str] | None:
        """Parse message text to extract command and query.

        Returns:
            Tuple of (mode, query) for learn/youtube/default modes,
            Tuple of (mode, query, args) for schedule/remind commands,
            Tuple of (mode, args) for note commands,
            or None for default mode.
        """
        text = text.strip()

        if text.lower().startswith("/learn "):
            return ("learn", text[7:].strip())
        elif text.lower() == "/learn":
            return ("learn", "What would you like to learn about? Please provide a topic.")
        elif text.lower().startswith("/youtube "):
            return ("youtube", text[9:].strip())
        elif text.lower() == "/youtube":
            return ("youtube", "Please provide a YouTube URL or tell me what you'd like to know about a video.")
        elif text.lower().startswith("/schedule "):
            return self._parse_schedule_command(text[10:])
        elif text.lower() == "/schedule":
            return ("schedule", "Usage: /schedule <time> <agent> [prompt]")
        elif text.lower().startswith("/remind "):
            return self._parse_remind_command(text[8:])
        elif text.lower() == "/remind":
            return ("remind", "Usage: /remind <time> <prompt>")
        elif text.lower().startswith("/note "):
            return ("note", text[6:].strip())
        elif text.lower() == "/note":
            return ("note", "Please provide the note content.")
        elif text.lower() == "/notes":
            return ("notes", None)
        else:
            return ("default", text)

    def _parse_schedule_command(self, text: str) -> tuple[str, str, str] | None:
        """Parse schedule command.

        Format: /schedule <time> <agent> [prompt]
        """
        parts = text.split(maxsplit=3)
        if len(parts) < 2:
            return None
        time_str = parts[0]
        agent = parts[1] if len(parts) > 1 else None
        prompt = " ".join(parts[2:]) if len(parts) > 2 else None
        return "schedule", time_str, agent, prompt

    def _parse_remind_command(self, text: str) -> tuple[str, str, str] | None:
        """Parse remind command.

        Format: /remind <time> <prompt>
        """
        parts = text.split(maxsplit=2)
        if len(parts) < 2:
            return None
        time_str = parts[0]
        prompt = parts[1] if len(parts) > 1 else None
        return "remind", time_str, prompt

    async def _handle_schedule(self, mode: str, time_str: str, agent: str, prompt: str) -> None:
        """Handle schedule command - create a scheduled task."""
        task_repo, note_repo = self._get_storage_repos()
        if task_repo is None:
            outgoing = OutgoingMessage(
                text="Storage package not available. Please install agntrick-storage.",
                recipient_id=self.channel.user_id,
            )
            await self.channel.send(outgoing)
            return

        # Use inlined storage module
        from agntrick_whatsapp.storage import Database, TaskRepository
        from agntrick_whatsapp.storage.models import ScheduledTask, TaskType
        from agntrick_whatsapp.storage.scheduler import parse_natural_time

        db = Database(self._storage_db_path)
        task_repo = TaskRepository(db)

        parsed_time, cron_expr = parse_natural_time(time_str)
        execute_at = parsed_time.timestamp()

        task = ScheduledTask(
            action_type=TaskType.RUN_AGENT,
            action_agent=agent,
            action_prompt=prompt,
            execute_at=execute_at,
            cron_expression=cron_expr,
        )

        task_repo.save(task)
        logger.info(f"Created task: {task.id} at {execute_at}")

        outgoing = OutgoingMessage(
            text=f"✓ Scheduled! {task.action_type}: {agent} at {parsed_time}",
            recipient_id=self.channel.user_id,
        )
        await self.channel.send(outgoing)

    async def _handle_remind(self, mode: str, time_str: str, prompt: str) -> None:
        """Handle remind command - same as schedule but creates task immediately."""
        await self._handle_schedule(mode, time_str, prompt)

    async def _handle_note(self, content: str) -> None:
        """Handle note command - save a note."""
        task_repo, note_repo = self._get_storage_repos()
        if note_repo is None:
            outgoing = OutgoingMessage(
                text="Storage package not available. Please install agntrick-storage.",
                recipient_id=self.channel.user_id,
            )
            await self.channel.send(outgoing)
            return

        # Use inlined storage module
        from agntrick_whatsapp.storage import Database, NoteRepository
        from agntrick_whatsapp.storage.models import Note

        db = Database(self._storage_db_path)
        note_repo = NoteRepository(db)

        note = Note(content=content)
        note_repo.save(note)
        logger.info(f"Saved note: {note.id}")

        outgoing = OutgoingMessage(
            text=f"✓ Note saved!",
            recipient_id=self.channel.user_id,
        )
        await self.channel.send(outgoing)

    async def _handle_notes(self) -> None:
        """Handle notes command - list all notes."""
        task_repo, note_repo = self._get_storage_repos()
        if note_repo is None:
            outgoing = OutgoingMessage(
                text="Storage package not available. Please install agntrick-storage.",
                recipient_id=self.channel.user_id,
            )
            await self.channel.send(outgoing)
            return

        # Use inlined storage module
        from agntrick_whatsapp.storage import Database, NoteRepository

        db = Database(self._storage_db_path)
        note_repo = NoteRepository(db)

        notes = note_repo.list_all()

        if not notes:
            outgoing = OutgoingMessage(
                text="No notes saved yet. Use /note <content> to save one.",
                recipient_id=self.channel.user_id,
            )
            await self.channel.send(outgoing)
            return

        note_list = "\n\n".join(
            f"{i + 1}. {note.content[:50]}..." if len(note.content) > 50 else note.content
            for i, note in enumerate(notes[:10], 1)
        )

        outgoing = OutgoingMessage(
            text=f"*Notes ({len(notes)}):*\n\n{note_list}",
            recipient_id=self.channel.user_id,
        )
        await self.channel.send(outgoing)

    async def start(self) -> None:
        """Start= WhatsApp router agent."""
        if self._running:
            logger.warning("Agent is already running")
            return

        logger.info("Starting WhatsApp router agent...")
        try:
            await self.channel.initialize()

            # Set up MCP servers
            if self._mcp_servers_override is not None:
                self._mcp_servers = self._mcp_servers_override
            else:
                # Default MCP servers for WhatsApp agent
                self._mcp_servers = (
                    AgentRegistry.get_mcp_servers("whatsapp-messenger")
                    or ["fetch"]
                )

            if self._mcp_servers:
                # Create MCP provider that manages all servers
                self._mcp_provider = MCPProvider(server_names=self._mcp_servers)
                # Create long-lived session for connection reuse across messages
                # Enter= context manager and keep it open for= agent lifetime
                self._mcp_session_cm = self._mcp_provider.tool_session(fail_fast=False)
                self._mcp_session = await self._mcp_session_cm.__aenter__()
                self._mcp_tools = self._mcp_session
                logger.info(f"Loaded {len(self._mcp_tools)} MCP tools in long-lived session")
            else:
                logger.info("No MCP servers configured, running with LLM only")

            self._running = True
            await self.channel.listen(self._handle_message)

        except Exception as e:
            logger.error(f"Failed to start WhatsApp router agent: {e}")
            self._running = False
            raise

    async def _handle_message(self, incoming: IncomingMessage) -> None:
        """Handle an incoming message from WhatsApp."""
        try:
            logger.info(f"Processing message from {incoming.sender_id}")

            # Check for audio
            is_audio = incoming.raw_data.get("is_audio", False)
            message_text = incoming.text

            if is_audio:
                await self._handle_audio(incoming)
                return

            # Parse command
            parsed = self._parse_command(message_text)
            logger.info(f"Routing to: {parsed}")

            # Handle different command types
            if parsed is None:
                mode = "default"
                query = message_text
                args = None
            elif len(parsed) == 2:
                mode, query = parsed
                args = None
            elif parsed[0] in ("schedule", "remind"):
                mode, time_str, agent_or_prompt = parsed[1]
                args = parsed[2:] if len(parsed) > 3 else None
            elif parsed[0] == "note":
                mode, content = parsed
                args = None
            elif parsed[0] == "notes":
                mode = parsed[0]
                args = None
            else:
                mode, query = parsed
                args = None

            # Get appropriate system prompt
            if mode == "learn":
                system_prompt = LEARNING_SYSTEM_PROMPT
            elif mode == "youtube":
                system_prompt = YOUTUBE_SYSTEM_PROMPT
            else:
                system_prompt = DEFAULT_SYSTEM_PROMPT

            # Handle different command types
            if mode in ("schedule", "remind"):
                await self._handle_schedule(mode, time_str, agent_or_prompt, args)
            elif mode == "note":
                await self._handle_note(content)
            elif mode == "notes":
                await self._handle_notes()
            elif mode in ("learn", "youtube", "default"):
                messages = [HumanMessage(content=query)]
                result = await self._get_or_create_graph(
                    mode, system_prompt, self._mcp_tools
                )
                response_text = str(result["messages"][-1].content)
                # Send response
                outgoing = OutgoingMessage(
                    text=response_text, recipient_id=incoming.sender_id
                )
                await self.channel.send(outgoing)
                logger.info(f"Response sent to {incoming.sender_id}")

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")

            try:
                # Provide more specific error messages for common issues
                error_msg = "Sorry, something went wrong. Please try again."
                if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                    error_msg = (
                        "Sorry, the request took too long. The service "
                        "might be slow or the URL might not be accessible. "
                        "Please try again."
                    )
                elif "connection" in str(e).lower() or "network" in str(e).lower():
                    error_msg = (
                        "Sorry, I couldn't connect to the service. "
                        "Please check your connection and try again."
                    )
                error_message = OutgoingMessage(
                    text=error_msg,
                    recipient_id=incoming.sender_id,
                )
                await self.channel.send(error_message)

            except Exception as send_error:
                logger.error(f"Failed to send error message: {send_error}")

    async def _handle_audio(self, incoming: IncomingMessage) -> None:
        """Handle audio message transcription."""
        audio_path = incoming.raw_data.get("audio_path")
        audio_mime_type = incoming.raw_data.get("audio_mime_type")

        if not audio_path or not isinstance(audio_path, str):
            outgoing = OutgoingMessage(
                text="Sorry, I couldn't process your audio message.",
                recipient_id=incoming.sender_id,
            )
            await self.channel.send(outgoing)
            return

        # Transcribe
        if self._audio_transcriber_config:
            transcriber = AudioTranscriber(
                config_file=self._audio_transcriber_config.config_file,
                model=self._audio_transcriber_config.model,
                timeout=self._audio_transcriber_config.timeout,
            )
        else:
            transcriber = AudioTranscriber()

        transcription = await transcriber.transcribe_audio(audio_path, audio_mime_type)

        # Clean up temp file
        try:
            import os
            os.unlink(audio_path)
        except Exception as e:
            logger.warning(f"Failed to clean up audio file: {e}")

        # Send transcription
        if transcription.startswith("Error:"):
            response_text = f"Sorry, I couldn't transcribe your audio. {transcription}"
        else:
            response_text = transcription

        outgoing = OutgoingMessage(
            text=response_text,
            recipient_id=incoming.sender_id,
        )
        await self.channel.send(outgoing)

    async def stop(self) -> None:
        """Stop= WhatsApp router agent."""
        if not self._running:
            return

        logger.info("Stopping WhatsApp router agent...")
        self._running = False
        self._shutdown_event.set()

        try:
            # Close MCP connections if provider exists
            if hasattr(self, "_mcp_session_cm") and self._mcp_session_cm is not None:
                logger.info("Closing MCP session...")
                await self._mcp_session_cm.__aexit__(None, None, None)
                logger.info("MCP session closed")

            await self.channel.shutdown()

        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

        logger.info("WhatsApp router agent stopped")
