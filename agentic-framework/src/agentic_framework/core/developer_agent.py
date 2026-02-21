from typing import Any, Sequence

from langchain_core.tools import StructuredTool

from agentic_framework.constants import BASE_DIR
from agentic_framework.core.langgraph_agent import LangGraphMCPAgent
from agentic_framework.registry import AgentRegistry
from agentic_framework.tools import (
    CodeSearcher,
    FileEditorTool,
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

## AVAILABLE TOOLS

1. **find_files** - Fast file search by name using fd
2. **discover_structure** - Directory tree exploration
3. **get_file_outline** - Extract class/function signatures (Python, JS, TS, Rust, Go, Java, C/C++, PHP)
4. **read_file_fragment** - Read specific line ranges (format: 'path:start:end')
5. **code_search** - Fast pattern search via ripgrep
6. **edit_file** - Edit files with line-based or text-based operations
7. **webfetch** (MCP) - Fetch web content

## MANDATORY FILE EDITING WORKFLOW

Before using edit_file, you MUST follow this sequence:

### Step 1: READ FIRST (Required)
- Use `read_file_fragment` to see the EXACT lines you plan to modify
- NEVER guess line numbers - always verify them first
- Example: read_file_fragment("example.py:88:95")

### Step 2: COPY EXACTLY
When providing replacement content:
- Copy the EXACT text including all quotes, indentation, and punctuation
- Do NOT truncate, paraphrase, or summarize
- Preserve docstring delimiters (\"\"\" or \'\'\')
- Maintain exact indentation (tabs vs spaces)

### Step 3: APPLY EDIT
Use edit_file with the appropriate format:

Line-based operations:
- replace:path:start:end:content
- insert:path:after_line:content
- delete:path:start:end

Text-based operation (RECOMMENDED - no line numbers needed):
{"op": "search_replace", "path": "file.py", "old": "exact text to find", "new": "replacement text"}

### Step 4: VERIFY
After editing:
- Check the result message for SYNTAX WARNING
- If warning appears, read the affected lines and fix immediately
- Do not exceed 3 retry attempts

### Error Recovery
If edit_file returns an error:
1. READ the file first using read_file_fragment
2. Understand what went wrong from the error message
3. Apply a corrected edit

## GENERAL GUIDELINES

- When finding files by name, use `find_files`
- When exploring project structure, use `discover_structure`
- When explaining a file, start with `get_file_outline`
- Use `code_search` for fast global pattern matching

Always provide clear, concise explanations and suggest improvements when relevant.
"""

    def local_tools(self) -> Sequence[Any]:
        # Initialize tool instances with project root
        searcher = CodeSearcher(str(BASE_DIR))
        finder = FileFinderTool(str(BASE_DIR))
        explorer = StructureExplorerTool(str(BASE_DIR))
        outliner = FileOutlinerTool(str(BASE_DIR))
        reader = FileFragmentReaderTool(str(BASE_DIR))
        editor = FileEditorTool(str(BASE_DIR))

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
