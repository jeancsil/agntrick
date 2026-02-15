import subprocess
from typing import Any, Dict, List, Union

from agentic_framework.interfaces.base import Tool


class CodeSearcher(Tool):
    """Wraps ripgrep (rg) for ultra-fast codebase querying."""

    def __init__(self, root_dir: str):
        self.root_dir = root_dir

    @property
    def name(self) -> str:
        return "code_search"

    @property
    def description(self) -> str:
        return "Searches the codebase for a given pattern using ripgrep. Returns top 20 matches."

    def invoke(self, input_str: str) -> Any:
        """Executes a search across the codebase. input_str is the search query."""
        return self.grep_search(input_str)

    def grep_search(self, query: str, file_type: str = "py") -> Union[List[str], List[Dict[str, Any]]]:
        """
        Executes a search across the codebase.
        Returns matches with line numbers and snippets.
        """
        try:
            # -n: line numbers, -C 1: context, -t: type
            cmd = ["rg", "--json", "-t", file_type, query, self.root_dir]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)

            # Note: In a production framework, you'd parse the JSON stream from rg
            # For this MVP, we return a simplified string representation
            if result.returncode != 0:
                return []
            return result.stdout.splitlines()[:20]  # Limit to top 20 for token safety
        except FileNotFoundError:
            return ["Error: ripgrep (rg) is not installed on the host system."]
