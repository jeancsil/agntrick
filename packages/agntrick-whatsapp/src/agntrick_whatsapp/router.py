"""WhatsApp router agent for routing commands to different specialist agents.

This module provides a router that handles WhatsApp messages and routes them
to different specialist agents based on command prefixes (e.g., /learn).
"""

import asyncio
import logging
import traceback
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from agntrick.llm import get_default_model
from agntrick.mcp import MCPConnectionError, MCPProvider
from agntrick.registry import AgentRegistry
from agntrick.tools import YouTubeTranscriptTool
from agntrick_whatsapp.base import Channel, IncomingMessage, OutgoingMessage
from agntrick_whatsapp.config import AudioTranscriberConfig
from agntrick_whatsapp.transcriber import AudioTranscriber

logger = logging.getLogger(__name__)


# System prompts for different agent modes
DEFAULT_SYSTEM_PROMPT = """You are a helpful AI assistant communicating through WhatsApp.
Be concise and friendly in your responses.
Avoid overly long explanations.
Use emojis occasionally to be more conversational.
If you need to show code or data, use formatted text blocks.
Focus on being helpful and direct.

CAPABILITIES:
- You have access to web search (DuckDuckGo) and web content fetching tools
- Use these tools to find current information and provide helpful answers
- When searching for news, always include the current year for better relevance

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
- Present yourself simply as a helpful assistant, not a technical system"""


LEARNING_SYSTEM_PROMPT = """You are an expert educator and tutorial creator communicating through WhatsApp.
Your specialty is breaking down complex topics into clear, step-by-step tutorials.

YOUR APPROACH:
1. Start with a brief overview of what the user will learn
2. Break down the topic into logical steps
3. Provide clear explanations for each step
4. Include practical examples when relevant
5. Anticipate common questions and address them

CAPABILITIES:
- You have access to web search (DuckDuckGo) and web content fetching tools
- Use these tools to find current information and best practices
- When searching, include the current year for relevance

WHATSAPP FORMAT GUIDELINES:
- Keep messages concise (WhatsApp is for quick communication)
- Use *bold* for emphasis
- Use numbered lists (1. 2. 3.) for steps
- Use code blocks with backticks for code
- Break long tutorials into multiple messages if needed

COMMUNICATION STYLE:
- Be encouraging and patient
- Explain technical terms simply
- Use analogies to make concepts relatable
- Keep explanations thorough but not verbose

Always prioritize clarity and practical application."""


YOUTUBE_SYSTEM_PROMPT = """You are a YouTube video analyst specialized in extracting
insights from video transcripts through WhatsApp.

Your capabilities:
1. **Summarization**: Provide concise, accurate summaries of video content
2. **Q&A**: Answer specific questions about topics covered in videos
3. **Key Points**: Extract main ideas with relevant timestamps
4. **Analysis**: Identify themes, arguments, and conclusions
5. **Comparison**: Compare content across multiple videos when asked

Guidelines:
- Always cite timestamps when referencing specific content
- Distinguish between facts stated in the video and your analysis
- If a video lacks captions, inform the user gracefully
- For long videos, organize summaries into sections with timestamps
- When asked about specific topics, quote relevant parts directly
- Keep responses concise for WhatsApp messaging

Use the youtube_transcript tool to fetch video transcripts, then provide
thoughtful analysis based on the transcript content."""


class WhatsAppRouterAgent:
    """WhatsApp agent that routes commands to different specialist modes.

    This agent handles WhatsApp communication and routes messages to different
    specialist behaviors based on command prefixes.

    Supported commands:
    - /learn <topic> - Use learning/tutorial mode
    - /youtube <url|query> - Use YouTube analysis mode
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

    def __init__(  # type: ignore[override]
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

        # Agent graphs for different modes (lazy initialized)
        self._graphs: dict[str, Any] = {}
        self._mcp_tools: list[Any] = []
        self._mcp_servers: list[str] = []

        logger.info(f"WhatsAppRouterAgent initialized with model={model_name or get_default_model()}")

    async def _load_mcp_tools_gracefully(self) -> list[Any]:
        """Load MCP tools with graceful error handling."""
        loaded_tools: list[Any] = []

        for server_name in self._mcp_servers:
            try:
                logger.info(f"Connecting to MCP server: {server_name}...")
                provider = MCPProvider(server_names=[server_name])
                tools = await provider.get_tools()
                loaded_tools.extend(tools)
                logger.info(f"✓ Connected to {server_name}: {len(tools)} tools loaded")
            except MCPConnectionError as e:
                logger.warning(f"✗ Failed to connect to {server_name}: {e}")
            except Exception as e:
                logger.warning(f"✗ Unexpected error connecting to {server_name}: {e}")

        return loaded_tools

    async def _get_or_create_graph(self, mode: str, system_prompt: str) -> Any:
        """Get or create an agent graph for the given mode."""
        if mode not in self._graphs:
            tools = list(self._mcp_tools)

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

            self._graphs[mode] = create_agent(
                model=self.model,
                tools=tools,
                # system_prompt=system_prompt,
                checkpointer=InMemorySaver(),
            )
        return self._graphs[mode]

    def _parse_command(self, text: str) -> tuple[str, str]:
        """Parse message text to extract command and query.

        Returns:
            Tuple of (mode, query) where mode is 'learn', 'youtube', or 'default'.
        """
        text = text.strip()

        if text.lower().startswith("/learn "):
            return "learn", text[7:].strip()
        elif text.lower() == "/learn":
            return "learn", "What would you like to learn about? Please provide a topic."
        elif text.lower().startswith("/youtube "):
            return "youtube", text[9:].strip()
        elif text.lower() == "/youtube":
            return "youtube", "Please provide a YouTube URL or tell me what you'd like to know about a video."
        else:
            return "default", text

    async def start(self) -> None:
        """Start the WhatsApp router agent."""
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
                self._mcp_servers = AgentRegistry.get_mcp_servers("whatsapp-messenger") or ["fetch", "hacker-news", "web-forager"]

            if self._mcp_servers:
                self._mcp_tools = await self._load_mcp_tools_gracefully()
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
            mode, query = self._parse_command(message_text)
            logger.info(f"Routing to mode: {mode}")

            # Get appropriate system prompt
            if mode == "learn":
                system_prompt = LEARNING_SYSTEM_PROMPT
            elif mode == "youtube":
                system_prompt = YOUTUBE_SYSTEM_PROMPT
            else:
                system_prompt = DEFAULT_SYSTEM_PROMPT

            # Add date context
            from datetime import datetime

            current_date = datetime.now()
            date_context = f"CURRENT DATE: {current_date.strftime('%Y-%m-%d')}\nCurrent year: {current_date.year}\n\n"
            full_prompt = date_context + system_prompt

            # Get or create graph for this mode
            graph = await self._get_or_create_graph(mode, full_prompt)

            # Run the agent
            messages = [HumanMessage(content=query)]
            result = await graph.ainvoke(
                {"messages": messages},
                config={"configurable": {"thread_id": f"whatsapp-{mode}"}},
            )
            response_text = str(result["messages"][-1].content)

            # Send response
            outgoing = OutgoingMessage(text=response_text, recipient_id=incoming.sender_id)
            await self.channel.send(outgoing)

            logger.info(f"Response sent to {incoming.sender_id}")

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")

            try:
                error_message = OutgoingMessage(
                    text="Sorry, something went wrong. Please try again.",
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

        outgoing = OutgoingMessage(text=response_text, recipient_id=incoming.sender_id)
        await self.channel.send(outgoing)

    async def stop(self) -> None:
        """Stop the WhatsApp router agent."""
        if not self._running:
            return

        logger.info("Stopping WhatsApp router agent...")
        self._running = False
        self._shutdown_event.set()

        try:
            await self.channel.shutdown()
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

        logger.info("WhatsApp router agent stopped")
