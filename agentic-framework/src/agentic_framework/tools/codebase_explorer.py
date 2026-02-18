import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from agentic_framework.interfaces.base import Tool

# Language detection by file extension
LANGUAGE_EXTENSIONS: Dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".php": "php",
}

# Regex patterns for each language
# Each pattern captures the relevant code construct
LANGUAGE_PATTERNS: Dict[str, List[str]] = {
    "python": [
        r"^\s*(class\s+\w+.*?)[:\(]",
        r"^\s*(async\s+def\s+\w+.*?)\(",
        r"^\s*(def\s+\w+.*?)\(",
    ],
    "javascript": [
        r"^\s*(export\s+)?(default\s+)?(class\s+\w+)",
        r"^\s*(export\s+)?(default\s+)?(function\s*\*?\s+\w+)",
        r"^\s*(export\s+)?(const\s+\w+\s*=\s*\([^)]*\)\s*=>)",
        r"^\s*(export\s+)?(const\s+\w+\s*=\s*async\s*\([^)]*\)\s*=>)",
    ],
    "typescript": [
        r"^\s*(export\s+)?(default\s+)?(class\s+\w+)",
        r"^\s*(export\s+)?(default\s+)?(function\s*\*?\s+\w+)",
        r"^\s*(export\s+)?(const\s+\w+\s*=\s*\([^)]*\)\s*=>)",
        r"^\s*(export\s+)?(const\s+\w+\s*=\s*async\s*\([^)]*\)\s*=>)",
        r"^\s*(export\s+)?(interface\s+\w+)",
        r"^\s*(export\s+)?(type\s+\w+)",
        r"^\s*(export\s+)?(enum\s+\w+)",
        r"^\s*(export\s+)?(abstract\s+class\s+\w+)",
        r"^\s*(export\s+)?(namespace\s+\w+)",
    ],
    "rust": [
        r"^\s*(pub\s+(\([^)]+\)\s+)?)?(struct\s+\w+)",
        r"^\s*(pub\s+)?(enum\s+\w+)",
        r"^\s*(pub\s+)?(trait\s+\w+)",
        r"^\s*(pub\s+(\([^)]+\)\s+)?)?(async\s+)?(fn\s+\w+)",
        r"^\s*(impl\s+(<[^>]+>\s+)?\w+)",
        r"^\s*(pub\s+)?(mod\s+\w+)",
    ],
    "go": [
        r"^\s*func\s+\(\w+\s+\*?\w+\)\s*\w+",  # method with receiver
        r"^\s*func\s+\w+",  # function
        r"^\s*type\s+\w+\s+struct\b",
        r"^\s*type\s+\w+\s+interface\b",
        r"^\s*type\s+\w+\s+func\b",
        r"^\s*type\s+\w+\s*\(",  # type alias with params
    ],
    "java": [
        r"^\s*(public|private|protected)?\s*(abstract\s+)?(class\s+\w+)",
        r"^\s*(public\s+)?(interface\s+\w+)",
        r"^\s*(public\s+)?(enum\s+\w+)",
        r"^\s*@\w+(\([^)]*\))?\s*$",  # annotations (standalone)
        r"^\s*(public|private|protected)\s+(static\s+)?[\w<>?,\s]+\s+\w+\s*\(",  # methods
        r"^\s*(public|private|protected)\s+\w+\s*\([^\)]*\)\s*\{",  # constructors
    ],
    "c": [
        r"^\s*(typedef\s+)?(struct\s+\w*)",
        r"^\s*(typedef\s+)?(enum\s+\w*)",
        r"^\s*(typedef\s+)?(union\s+\w*)",
        r"^\s*(void|int|char|float|double|long|unsigned|signed|short)\s+[\w\s\*]+\s*\w+\s*\(",
    ],
    "cpp": [
        r"^\s*(typedef\s+)?(struct\s+\w*)",
        r"^\s*(typedef\s+)?(enum\s+\w*)",
        r"^\s*(typedef\s+)?(union\s+\w*)",
        r"^\s*(class\s+\w+)",
        r"^\s*(namespace\s+\w+)",
        r"^\s*(template\s*<[^>]*>)?\s*class\s+\w+",  # template class
        r"^\s*(template\s*<[^>]*>)?\s*[\w:]+\s+[\w:]+\s*\(",  # template function
    ],
    "php": [
        r"^\s*(abstract\s+)?(final\s+)?(class\s+\w+)",
        r"^\s*(interface\s+\w+)",
        r"^\s*(trait\s+\w+)",
        r"^\s*(public|private|protected)?\s*(static\s+)?function\s+\w+",
    ],
}


class CodebaseExplorer:
    """
    A utility for agents to discover and navigate codebases.
    Base class for specific codebase tools.
    """

    def __init__(self, root_dir: Union[str, Path], ignore_patterns: Optional[List[str]] = None):
        self.root_dir = Path(root_dir).resolve()
        # Standard noise reduction for agentic context
        self.ignore_patterns = ignore_patterns or [
            r"\.git",
            r"__pycache__",
            r"node_modules",
            r"\.venv",
            r"dist",
            r"build",
            r"\.mypy_cache",
            r"\.pytest_cache",
        ]

    def _is_ignored(self, path: Path) -> bool:
        try:
            rel_path = str(path.relative_to(self.root_dir))
        except ValueError:
            return True
        return any(re.search(pattern, rel_path) for pattern in self.ignore_patterns)


class StructureExplorerTool(CodebaseExplorer, Tool):
    """Tool to discover the directory structure of the project."""

    @property
    def name(self) -> str:
        return "discover_structure"

    @property
    def description(self) -> str:
        return "Lists files and directories recursively up to a certain depth. Helps understand project layout."

    def invoke(self, input_str: str) -> Any:
        # Input can be max_depth as string, defaults to 3
        try:
            max_depth = int(input_str) if input_str.isdigit() else 3
        except Exception:
            max_depth = 3
        return self._build_tree(self.root_dir, depth=0, max_depth=max_depth)

    def _build_tree(self, current_dir: Path, depth: int, max_depth: int) -> Dict[str, Any]:
        tree: Dict[str, Any] = {"name": current_dir.name or str(current_dir), "type": "directory", "children": []}

        if depth >= max_depth:
            return tree

        try:
            for item in sorted(current_dir.iterdir()):
                if self._is_ignored(item):
                    continue

                if item.is_dir():
                    tree["children"].append(self._build_tree(item, depth + 1, max_depth))
                else:
                    tree["children"].append(
                        {"name": item.name, "type": "file", "size_kb": round(item.stat().st_size / 1024, 2)}
                    )
        except PermissionError:
            tree["error"] = "Permission denied"

        return tree


class FileOutlinerTool(CodebaseExplorer, Tool):
    """Tool to extract high-level signatures from various programming language files."""

    @property
    def name(self) -> str:
        return "get_file_outline"

    @property
    def description(self) -> str:
        return """Extracts classes, functions, and other definitions from code files.
        Supports: Python, JavaScript, TypeScript, Rust, Go, Java, C/C++, PHP.
        Returns a list of signatures with their line numbers.
        Output format: [{"line": 15, "signature": "class MyAgent:"}, ...]"""

    def invoke(self, file_path: str) -> Any:
        full_path = self.root_dir / file_path
        if not full_path.exists() or not full_path.is_file():
            return f"Error: File {file_path} not found."

        language = self._detect_language(file_path)
        if language is None:
            return f"Error: Unsupported file type for {file_path}. Supported: Python, JS/TS, Rust, Go, Java, C/C++, PHP"

        patterns = LANGUAGE_PATTERNS.get(language, [])
        return self._extract_outline(full_path, patterns)

    def _detect_language(self, file_path: str) -> Optional[str]:
        """Detect programming language from file extension."""
        ext = Path(file_path).suffix.lower()
        return LANGUAGE_EXTENSIONS.get(ext)

    def _extract_outline(self, file_path: Path, patterns: List[str]) -> List[Dict[str, Any]]:
        """Extract code outline using regex patterns."""
        outline: List[Dict[str, Any]] = []
        compiled_patterns = [re.compile(p) for p in patterns]

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                for line_num, line in enumerate(f, 1):
                    for pattern in compiled_patterns:
                        if pattern.search(line):
                            # Clean up the signature (limit length for readability)
                            signature = line.strip()
                            if len(signature) > 100:
                                signature = signature[:97] + "..."
                            outline.append({"line": line_num, "signature": signature})
                            break  # Only match first pattern per line
            return outline
        except Exception as e:
            return [{"error": f"Error reading file: {e}"}]


class FileFragmentReaderTool(CodebaseExplorer, Tool):
    """Tool to read a specific range of a file."""

    @property
    def name(self) -> str:
        return "read_file_fragment"

    @property
    def description(self) -> str:
        return "Reads a specific line range from a file. Input format: 'path:start:end' (e.g. 'src/cli.py:1:20')."

    def invoke(self, input_str: str) -> Any:
        try:
            parts = input_str.split(":")
            if len(parts) < 3:
                return "Error: Invalid input format. Use 'path:start:end'."
            file_path = ":".join(parts[:-2])
            start_line = int(parts[-2])
            end_line = int(parts[-1])

            full_path = self.root_dir / file_path
            if not full_path.exists():
                return f"Error: File {file_path} not found."

            with open(full_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                return "".join(lines[max(0, start_line - 1) : end_line])
        except Exception as e:
            return f"Error: {e}"


class FileFinderTool(CodebaseExplorer, Tool):
    """Tool to find files by name using 'fd'."""

    @property
    def name(self) -> str:
        return "find_files"

    @property
    def description(self) -> str:
        return (
            "Fast file search by name using 'fd'. Returns paths relative to project root. "
            "Input is a search pattern (regex or simple string)."
        )

    def invoke(self, pattern: str) -> Any:
        try:
            # First, get candidates using fd
            # -H: hidden files, -I: ignore .gitignore for faster full list if needed,
            # but usually we want to respect it, so let's stick to standard fd.
            # We'll list all files and let fzf rank them.
            fd_cmd = ["fd", "--color", "never", "-H", ".", str(self.root_dir)]
            fd_result = subprocess.run(fd_cmd, capture_output=True, text=True, check=False)

            if fd_result.returncode != 0:
                if fd_result.stderr:
                    return f"Error executing fd: {fd_result.stderr}"
                return "No files found."

            all_files = fd_result.stdout
            if not all_files:
                return "No files found."

            # Use fzf to rank the files based on the pattern
            # fzf -f performs a non-interactive fuzzy search
            try:
                fzf_cmd = ["fzf", "-f", pattern]
                fzf_result = subprocess.run(fzf_cmd, input=all_files, capture_output=True, text=True, check=False)
                if fzf_result.returncode == 0:
                    ranked_files = fzf_result.stdout.splitlines()
                else:
                    # Fallback to simple substring match if fzf returns nothing or fails
                    ranked_files = [f for f in all_files.splitlines() if pattern.lower() in f.lower()]
            except FileNotFoundError:
                # Fallback if fzf is missing
                ranked_files = [f for f in all_files.splitlines() if pattern.lower() in f.lower()]

            # Convert absolute paths back to relative and limit results
            relative_files = []
            for f in ranked_files[:30]:  # Limit to top 30
                try:
                    relative_files.append(str(Path(f).relative_to(self.root_dir)))
                except ValueError:
                    relative_files.append(f)

            if not relative_files:
                return "No matches found for the given pattern."

            return relative_files
        except FileNotFoundError:
            return "Error: Required search tools (fd) not found."
