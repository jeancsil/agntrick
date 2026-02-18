from typing import Any, Sequence

from langchain_core.tools import StructuredTool

from agentic_framework.constants import BASE_DIR
from agentic_framework.core.langgraph_agent import LangGraphMCPAgent
from agentic_framework.registry import AgentRegistry
from agentic_framework.tools import (
    CodeSearcher,
    FileFinderTool,
    FileFragmentReaderTool,
    FileOutlinerTool,
    StructureExplorerTool,
)


@AgentRegistry.register("developer", mcp_servers=["webfetch"])
class DeveloperAgent(LangGraphMCPAgent):
    """
    A specialized agent for codebase exploration and development.
    Equipped with tools to search, structure, and read code, plus MCP capabilities.
    """

    @property
    def system_prompt(self) -> str:
        return """You are a Principal Software Engineer assistant.
        Your goal is to help the user understand and maintain their codebase.
        You have access to several specialized tools for:
        1. Discovering the project structure and finding files by name (`find_files`).
        2. Extracting class and function outlines from code files (`get_file_outline`).
           Supports: Python, JavaScript, TypeScript, Rust, Go, Java, C/C++, PHP.
        3. Reading specific fragments of a file (`read_file_fragment`).
        4. Searching the codebase for patterns using ripgrep (`code_search`).

        When you need to find a specific file by name, use `find_files`.
        When asked about the project structure, start with `discover_structure`.
        When asked to explain a file, start with `get_file_outline` to get an overview.
        Use `read_file_fragment` to read specific lines if you need more detail.
        Use `code_search` for fast global pattern matching.

        Always provide clear, concise explanations and suggest improvements when relevant.
        You also have access to MCP tools like `webfetch` if you need to fetch information from the web.
        """

    def local_tools(self) -> Sequence[Any]:
        # Initialize tool instances with project root
        searcher = CodeSearcher(str(BASE_DIR))
        finder = FileFinderTool(str(BASE_DIR))
        explorer = StructureExplorerTool(str(BASE_DIR))
        outliner = FileOutlinerTool(str(BASE_DIR))
        reader = FileFragmentReaderTool(str(BASE_DIR))

        return [
            StructuredTool.from_function(
                func=searcher.invoke,
                name=searcher.name,
                description=searcher.description,
            ),
            StructuredTool.from_function(
                func=finder.invoke,
                name=finder.name,
                description=finder.description,
            ),
            StructuredTool.from_function(
                func=explorer.invoke,
                name=explorer.name,
                description=explorer.description,
            ),
            StructuredTool.from_function(
                func=outliner.invoke,
                name=outliner.name,
                description=outliner.description,
            ),
            StructuredTool.from_function(
                func=reader.invoke,
                name=reader.name,
                description=reader.description,
            ),
        ]
