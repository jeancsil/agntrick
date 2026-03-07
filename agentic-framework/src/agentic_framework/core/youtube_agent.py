"""YouTube video analysis agent with transcript extraction capabilities."""

import logging
from typing import Any, Sequence

from langchain_core.tools import StructuredTool

from agentic_framework.core.langgraph_agent import LangGraphMCPAgent
from agentic_framework.registry import AgentRegistry
from agentic_framework.tools.youtube_transcript import YouTubeTranscriptTool

logger = logging.getLogger(__name__)


@AgentRegistry.register("youtube", mcp_servers=["web-fetch"])
class YouTubeAgent(LangGraphMCPAgent):
    """YouTube video analysis agent.

    This agent specializes in extracting insights from YouTube videos
    through transcript analysis. It can summarize content, answer
    questions about specific topics, and provide timestamp references.

    Capabilities:
        - Extract and analyze video transcripts
        - Summarize video content concisely
        - Answer questions about specific parts
        - Identify key points with timestamps
        - Compare multiple videos
        - Extract quotes and citations

    Example Usage:
        bin/agent.sh youtube -i "Summarize https://youtube.com/watch?v=abc123"
        bin/agent.sh youtube -i "What does this video say about AI? https://..."
    """

    @property
    def system_prompt(self) -> str:
        """Return the system prompt for this agent.

        The system prompt defines the agent's behavior and capabilities.
        """
        return """You are a YouTube video analyst specialized in extracting
insights from video transcripts.

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

Use the youtube_transcript tool to fetch video transcripts, then provide
thoughtful analysis based on the transcript content.

If you need additional context, you can use web search to find related
information about the video or topics mentioned."""

    def local_tools(self) -> Sequence[Any]:
        """Return YouTube-specific tools.

        Returns:
            A sequence of tools available to the agent.
        """
        tool = YouTubeTranscriptTool()
        return [
            StructuredTool.from_function(
                func=tool.invoke,
                name=tool.name,
                description=tool.description,
            )
        ]
