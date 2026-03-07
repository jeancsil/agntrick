from pathlib import Path
from typing import Any, Sequence

from langchain_core.tools import StructuredTool

from agntrick.agent import AgentBase
from agntrick.prompts import load_prompt
from agntrick.registry import AgentRegistry
from agntrick.tools import (
    CodeSearcher,
    FileEditorTool,
    FileFinderTool,
    FileFragmentReaderTool,
    FileOutlinerTool,
    StructureExplorerTool,
)


@AgentRegistry.register("developer", mcp_servers=["fetch"])
class DeveloperAgent(AgentBase):
    """
    A specialized agent for codebase exploration and development.
    Equipped with tools to search, structure, and read code, plus MCP capabilities.
    """

    @property
    def system_prompt(self) -> str:
        return load_prompt("developer")

    def local_tools(self) -> Sequence[Any]:
        # Initialize tool instances with current working directory
        searcher = CodeSearcher(str(Path.cwd()))
        finder = FileFinderTool(str(Path.cwd()))
        explorer = StructureExplorerTool(str(Path.cwd()))
        outliner = FileOutlinerTool(str(Path.cwd()))
        reader = FileFragmentReaderTool(str(Path.cwd()))
        editor = FileEditorTool(str(Path.cwd()))

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
            StructuredTool.from_function(
                func=editor.invoke,
                name=editor.name,
                description=editor.description,
            ),
        ]
