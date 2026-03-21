# CommitterAgent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `CommitterAgent` that analyzes git changes and generates conventional commit messages.

**Architecture:** A local agent (no MCP servers) with a custom `GitCommandTool` that executes whitelisted git commands via subprocess. The agent uses its LLM to analyze git output and generate commit message suggestions.

**Tech Stack:** Python 3.12+, subprocess module (stdlib), existing agntrick AgentBase framework

---

## File Structure

```
src/agntrick/
├── agents/
│   └── committer.py              # NEW - CommitterAgent class
├── tools/
│   ├── git_command.py            # NEW - GitCommandTool class
│   └── __init__.py               # MODIFY - Add GitCommandTool export
├── prompts/
│   └── committer.md              # NEW - System prompt file
└── prompts.py                    # OPTIONAL - Add fallback prompt

tests/
├── test_git_command_tool.py      # NEW - Unit tests for GitCommandTool
└── test_committer_agent.py       # NEW - Integration tests for CommitterAgent
```

---

## Task 1: Create GitCommandTool (Core git operations)

**Files:**
- Create: `src/agntrick/tools/git_command.py`

**Dependencies:** None (uses stdlib)

**Reference:** Follow `src/agntrick/tools/example.py` pattern for Tool class structure

- [ ] **Step 1: Create file with imports and Tool base class**

```python
"""Git command tool for analyzing repository changes."""

import subprocess
from pathlib import Path
from typing import Any

from agntrick.interfaces.base import Tool


class GitCommandTool(Tool):
    """Execute git commands to analyze repository changes.

    Only whitelisted git commands are supported for security.
    All commands are executed with subprocess.run() using list arguments.
    """

    name = "git_command"
    description = "Execute git commands to analyze repository changes"

    # Whitelist of allowed git subcommands
    ALLOWED_COMMANDS = {"status", "diff", "log", "show", "branch"}

    def __init__(self, repo_path: str | None = None):
        """Initialize git tool.

        Args:
            repo_path: Path to git repository. Defaults to current directory.
        """
        self.repo_path = repo_path or str(Path.cwd())

    @property
    def name(self) -> str:
        return "git_command"

    @property
    def description(self) -> str:
        return "Execute git commands (status, diff, log, show, branch) to analyze repository changes"

    def invoke(self, input_str: str) -> str:
        """Execute a git command.

        Args:
            input_str: Git command (e.g., "status", "diff --cached", "log -5")

        Returns:
            Command output or error message
        """
        # Implementation in next step
        pass
```

- [ ] **Step 2: Run make check to verify basic structure**

Run: `make check`
Expected: May have unused import warnings, but structure should be valid

- [ ] **Step 3: Implement invoke method with full error handling**

Replace the `invoke` method placeholder with:

```python
    def invoke(self, input_str: str) -> str:
        """Execute a git command.

        Args:
            input_str: Git command (e.g., "status", "diff --cached", "log -5")

        Returns:
            Command output or error message
        """
        try:
            # Parse and validate command
            parts = input_str.strip().split()
            if not parts or parts[0] not in self.ALLOWED_COMMANDS:
                return f"Error: Unsupported git command. Allowed: {', '.join(sorted(self.ALLOWED_COMMANDS))}"

            # Build command with list arguments (no shell=True)
            cmd = ["git", "-C", self.repo_path] + parts

            # Execute with timeout
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return f"Error: {result.stderr.strip() or 'Git command failed'}"

            # Truncate large outputs (diffs can be huge)
            output = result.stdout
            if len(output.splitlines()) > 500:
                lines = output.splitlines()
                output = "\n".join(lines[:500])
                output += f"\n\n(... {len(lines) - 500} more lines truncated)"
                output += "\nTip: Use 'git diff <file>' for specific files or 'git diff --stat' for overview."

            return output

        except FileNotFoundError:
            return "Error: Not a git repository or git is not installed."
        except subprocess.TimeoutExpired:
            return "Error: Git command timed out."
        except Exception as e:
            return f"Error: {str(e)}"
```

- [ ] **Step 4: Run make check**

Run: `make check`
Expected: Should pass (mypy and ruff)

- [ ] **Step 5: Commit**

```bash
git add src/agntrick/tools/git_command.py
git commit -m "feat: add GitCommandTool for git operations

- Whitelisted commands: status, diff, log, show, branch
- Subprocess with list args (no shell=True)
- 30s timeout, 500 line truncation
- Error handling for not a repo, timeout, unsupported commands"
```

---

## Task 2: Export GitCommandTool from tools module

**Files:**
- Modify: `src/agntrick/tools/__init__.py`

- [ ] **Step 1: Add import statement**

Add this line at the top with other imports (after `from .example import...`):

```python
from .git_command import GitCommandTool
```

- [ ] **Step 2: Add to __all__ list**

Add `"GitCommandTool"` to the `__all__` list (alphabetically order: after `"FileEditorTool"`, before `"SyntaxValidator"`):

```python
__all__ = [
    "AgentInvocationTool",
    "CalculatorTool",
    "WeatherTool",
    "CodeSearcher",
    "StructureExplorerTool",
    "FileOutlinerTool",
    "FileFragmentReaderTool",
    "FileFinderTool",
    "FileEditorTool",
    "GitCommandTool",  # NEW
    "SyntaxValidator",
    "ValidationResult",
    "get_validator",
    "YouTubeTranscriptCache",
    "YouTubeTranscriptTool",
]
```

- [ ] **Step 3: Run make check**

Run: `make check`
Expected: Should pass

- [ ] **Step 4: Commit**

```bash
git add src/agntrick/tools/__init__.py
git commit -m "feat: export GitCommandTool from tools module"
```

---

## Task 3: Create committer system prompt

**Files:**
- Create: `prompts/committer.md`

**Reference:** Follow existing prompt pattern in `prompts/developer.md`

- [ ] **Step 1: Create system prompt file**

Create `prompts/committer.md` with:

```markdown
You are a Committer, a specialized assistant for analyzing git changes and generating conventional commit messages.

## Your Purpose

You help developers understand what they've changed and create clear, consistent commit messages following the Conventional Commits specification.

## Conventional Commit Format

Follow this format for commit messages:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat`: A new feature
- `fix`: A bug fix
- `docs`: Documentation only changes
- `style`: Changes that don't affect code meaning (formatting, etc.)
- `refactor`: Code change that neither fixes a bug nor adds a feature
- `perf`: Performance improvement
- `test`: Adding or updating tests
- `build`: Changes to build system or dependencies
- `ci`: CI/CD configuration changes
- `chore`: Other changes that don't modify src or test files
- `revert`: Revert a previous commit

**Breaking Changes:**
- Add `!` after type/scope: `feat(api)!: remove user endpoint`
- Or add `BREAKING CHANGE:` footer

**Subject:**
- Use imperative mood ("add" not "added" or "adds")
- Don't capitalize first letter
- No period at end
- Keep under 72 characters

## Your Capabilities

You have access to git commands:
- `status` - See repository status
- `diff` - Show unstaged changes
- `diff --cached` - Show staged changes
- `log` - Show commit history
- `show <commit>` - Show specific commit
- `branch` - Show current branch

## How to Respond

1. **When asked about changes:** Use `status` and `diff --cached` to see what's changed
2. **When asked for a commit message:** Analyze the changes and suggest a conventional commit message
3. **When asked about history:** Use `log` to show recent commits
4. **Always summarize:** Briefly explain what changed before suggesting commit messages

## Guidelines

- Be concise but thorough
- If no changes are staged, suggest using `git add`
- Focus on the "why" not just the "what"
- For multiple unrelated changes, suggest splitting into multiple commits
- Use the git_command tool for all git operations

## Example

User: "What's staged and suggest a commit message?"

1. Use `status` to see staged files
2. Use `diff --cached` to see the actual changes
3. Analyze and respond:
   - Summary: "You've modified 3 files adding user authentication..."
   - Suggestion: "feat(auth): add user login and registration"
```

- [ ] **Step 2: Commit**

```bash
git add prompts/committer.md
git commit -m "docs: add committer system prompt

- Conventional commits format
- Git command usage guidelines
- Response patterns and examples"
```

---

## Task 4: Create CommitterAgent class

**Files:**
- Create: `src/agntrick/agents/committer.py`

**Reference:** Follow `src/agntrick/agents/developer.py` pattern

- [ ] **Step 1: Create agent file with basic structure**

```python
"""CommitterAgent for analyzing git changes and generating commit messages."""

from pathlib import Path
from typing import Any, Sequence

from agntrick.agent import AgentBase
from agntrick.prompts import load_prompt
from agntrick.registry import AgentRegistry
from agntrick.tools.git_command import GitCommandTool


@AgentRegistry.register("committer")
class CommitterAgent(AgentBase):
    """Agent specialized in git operations and commit message generation."""

    @property
    def system_prompt(self) -> str:
        return load_prompt("committer")

    def local_tools(self) -> Sequence[Any]:
        # Tool defaults to current directory
        return [GitCommandTool().to_langchain_tool()]
```

- [ ] **Step 2: Run make check**

Run: `make check`
Expected: Should pass

- [ ] **Step 3: Commit**

```bash
git add src/agntrick/agents/committer.py
git add src/agntrick/agents/__init__.py  # May need to add import
git commit -m "feat: add CommitterAgent for git operations

- Analyzes git changes and generates commit messages
- Uses GitCommandTool for local git operations
- No MCP servers required (git only)
- Registered as 'committer'"
```

---

## Task 5: Write unit tests for GitCommandTool

**Files:**
- Create: `tests/test_git_command_tool.py`

**Reference:** Follow test patterns in `tests/test_ollama_agent.py`

- [ ] **Step 1: Create test file structure**

```python
"""Tests for GitCommandTool."""

import subprocess

from agntrick.tools.git_command import GitCommandTool


class TestGitCommandTool:
    """Tests for GitCommandTool."""

    def test_tool_has_correct_name(self):
        """Tool should have name 'git_command'."""
        tool = GitCommandTool()
        assert tool.name == "git_command"

    def test_tool_has_description(self):
        """Tool should have a description."""
        tool = GitCommandTool()
        assert len(tool.description) > 0

    def test_default_repo_path_is_cwd(self):
        """Default repo_path should be current directory."""
        tool = GitCommandTool()
        from pathlib import Path
        assert tool.repo_path == str(Path.cwd())

    def test_custom_repo_path(self):
        """Should accept custom repo_path."""
        tool = GitCommandTool(repo_path="/custom/path")
        assert tool.repo_path == "/custom/path"

    def test_invoke_empty_input_returns_error(self):
        """Empty input should return error."""
        tool = GitCommandTool()
        result = tool.invoke("")
        assert "Error: Unsupported git command" in result

    def test_invoke_unsupported_command_returns_error(self):
        """Unsupported commands should be rejected."""
        tool = GitCommandTool()
        result = tool.invoke("push origin main")
        assert "Error: Unsupported git command" in result
        assert "push" not in result  # Command name should not be in allowed list

    def test_status_command_executes(self, monkeypatch):
        """git status should execute successfully."""
        # Mock subprocess.run to return valid git output
        class MockResult:
            returncode = 0
            stdout = "On branch main\nnothing to commit"
            stderr = ""

        def mock_run(*args, **kwargs):
            return MockResult()

        monkeypatch.setattr("subprocess.run", mock_run)

        tool = GitCommandTool()
        result = tool.invoke("status")
        assert "On branch main" in result
        assert "nothing to commit" in result

    def test_git_error_returns_error_message(self, monkeypatch):
        """Git errors should be returned as error messages."""
        class MockResult:
            returncode = 1
            stdout = ""
            stderr = "fatal: not a git repository"

        def mock_run(*args, **kwargs):
            return MockResult()

        monkeypatch.setattr("subprocess.run", mock_run)

        tool = GitCommandTool()
        result = tool.invoke("status")
        assert result.startswith("Error:")
        assert "not a git repository" in result

    def test_timeout_handling(self, monkeypatch):
        """Command timeout should return timeout error."""
        import subprocess

        def mock_run(*args, **kwargs):
            raise subprocess.TimeoutExpired("git", 30)

        monkeypatch.setattr("subprocess.run", mock_run)

        tool = GitCommandTool()
        result = tool.invoke("status")
        assert "Error: Git command timed out" in result

    def test_large_output_truncated(self, monkeypatch):
        """Large outputs should be truncated after 500 lines."""
        class MockResult:
            returncode = 0
            # Create 600 lines of output
            stdout = "\n".join([f"Line {i}" for i in range(600)])
            stderr = ""

        def mock_run(*args, **kwargs):
            return MockResult()

        monkeypatch.setattr("subprocess.run", mock_run)

        tool = GitCommandTool()
        result = tool.invoke("log")
        assert "100 more lines truncated" in result
        assert "git diff <file>" in result
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_git_command_tool.py -v`
Expected: Should pass (we mocked subprocess)

- [ ] **Step 3: Commit**

```bash
git add tests/test_git_command_tool.py
git commit -m "test: add GitCommandTool unit tests

- Test tool name, description, repo_path
- Test command validation and error handling
- Test subprocess mocking for status, errors, timeout
- Test output truncation for large diffs"
```

---

## Task 6: Write integration tests for CommitterAgent

**Files:**
- Create: `tests/test_committer_agent.py`

- [ ] **Step 1: Create integration test file**

```python
"""Tests for CommitterAgent."""

from agntrick.agents.committer import CommitterAgent
from agntrick.registry import AgentRegistry


class TestCommitterAgent:
    """Tests for CommitterAgent."""

    def test_agent_is_registered(self):
        """CommitterAgent should be registered in AgentRegistry."""
        agent_cls = AgentRegistry.get("committer")
        assert agent_cls is CommitterAgent

    def test_system_prompt_loads_committer_prompt(self):
        """Agent should load committer.md prompt."""
        agent = CommitterAgent()
        prompt = agent.system_prompt

        # Should contain committer-specific content
        assert "Committer" in prompt
        assert "conventional commit" in prompt.lower()
        assert "git_command" in prompt

    def test_system_prompt_not_empty(self):
        """System prompt should not be empty."""
        agent = CommitterAgent()
        assert len(agent.system_prompt) > 100

    def test_local_tools_includes_git_command(self):
        """Agent should have GitCommandTool."""
        agent = CommitterAgent()
        tools = agent.local_tools()

        tool_names = [t.name for t in tools]
        assert "git_command" in tool_names

    def test_git_command_tool_has_correct_description(self):
        """GitCommandTool should have git-related description."""
        agent = CommitterAgent()
        tools = agent.local_tools()

        git_tool = next(t for t in tools if t.name == "git_command")
        assert "git" in git_tool.description.lower()
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_committer_agent.py -v`
Expected: Should pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_committer_agent.py
git commit -m "test: add CommitterAgent integration tests

- Test agent registration in AgentRegistry
- Test system prompt loads correctly
- Test GitCommandTool is included in local_tools
- Verify prompt contains committer-specific content"
```

---

## Task 7: Run full test suite and fix issues

- [ ] **Step 1: Run full test suite**

Run: `make test`

Expected: All tests pass, coverage maintained (80%+)

- [ ] **Step 2: If tests fail, debug and fix**

Run: `pytest tests/test_git_command_tool.py tests/test_committer_agent.py -v --tb=short`

- [ ] **Step 3: Check coverage**

Run: `pytest --cov=src/agntrick/tools/git_command --cov=src/agntrick/agents/committer --cov-report=term-missing`

Expected: High coverage (aim for 80%+)

- [ ] **Step 4: Commit any fixes**

```bash
git add src/agntrick/tools/git_command.py src/agntrick/agents/committer.py
git commit -m "fix: address test failures and improve coverage"
```

---

## Task 8: Run linting and fix issues

- [ ] **Step 1: Run make check**

Run: `make check`

Expected: No mypy or ruff errors

- [ ] **Step 2: Fix any linting issues**

If mypy fails:
- Check type hints
- Ensure imports are correct

If ruff fails:
- Check import ordering
- Fix unused variables

- [ ] **Step 3: Commit linting fixes**

```bash
git add src/agntrick/tools/git_command.py src/agntrick/agents/committer.py
git commit -m "style: fix linting issues"
```

---

## Task 9: Test agent manually via CLI

- [ ] **Step 1: Test basic agent invocation**

Run: `agntrick committer -i "help"`

Expected: Agent responds helpfully

- [ ] **Step 2: Test git status**

Run: `agntrick committer -i "what's the git status?"`

Expected: Agent uses git_command tool to show status

- [ ] **Step 3: Test commit message generation**

Stage a file and run:
```bash
echo "# Test" >> README.md
git add README.md
agntrick committer -i "what's staged and suggest a commit message?"
```

Expected: Agent analyzes changes and suggests commit message

- [ ] **Step 4: Test git log**

Run: `agntrick committer -i "show last 3 commits"`

Expected: Agent shows commit history

- [ ] **Step 5: Commit working implementation**

```bash
git add .  # If any manual fixes needed
git commit -m "test: verify CommitterAgent works via CLI

- Tested: help, status, commit message generation, log
- Agent correctly uses GitCommandTool
- All scenarios working as expected"
```

---

## Task 10: Update README.md

**Files:**
- Modify: `README.md`

**Reference:** Add to Available Agents table following existing pattern

- [ ] **Step 1: Find the agents table in README.md**

Look for the table listing agents (developer, news, etc.)

- [ ] **Step 2: Add committer entry**

Add to the agents table:

```markdown
| committer | Analyze git changes and generate conventional commit messages | Git operations (status, diff, log, show, branch) | No |
```

- [ ] **Step 3: Run make check**

Run: `make check`
Expected: Should pass

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add committer agent to README

- List committer in Available Agents table
- Document git operations capability
- Note: no MCP servers required"
```

---

## Task 11: Final verification

- [ ] **Step 1: Run final make check**

Run: `make check`
Expected: PASS

- [ ] **Step 2: Run final make test**

Run: `make test`
Expected: All tests PASS, coverage 80%+

- [ ] **Step 3: Verify all files created**

Run:
```bash
ls -la src/agntrick/tools/git_command.py
ls -la src/agntrick/agents/committer.py
ls -la prompts/committer.md
ls -la tests/test_git_command_tool.py
ls -la tests/test_committer_agent.py
```

Expected: All files exist

- [ ] **Step 4: Final commit if needed**

```bash
git add .
git commit -m "feat: complete CommitterAgent implementation

- GitCommandTool with whitelisted commands
- CommitterAgent for git analysis and commit messages
- Comprehensive test coverage
- Documentation in README.md"
```

---

## Success Criteria Checklist

After completing all tasks, verify:

- [ ] `agntrick committer -i "help"` works
- [ ] `agntrick committer -i "show git status"` works
- [ ] `agntrick committer -i "suggest commit message"` works
- [ ] `agntrick committer -i "show last 5 commits"` works
- [ ] All tests pass (`make test`)
- [ ] Linting passes (`make check`)
- [ ] Coverage maintained at 80%+
- [ ] README.md updated with new agent

---

## Notes for Implementation

1. **Subprocess Mocking:** Use `monkeypatch.setattr("subprocess.run", ...)` for testing subprocess calls
2. **Path Handling:** `Path.cwd()` gives current working directory at runtime
3. **Git Commands:** Always use list arguments with `subprocess.run()` - never `shell=True`
4. **Error Messages:** Always return error strings, never raise exceptions from Tool.invoke()
5. **Type Hints:** Use `str | None` syntax (Python 3.10+)
6. **Agent Registry:** The `@AgentRegistry.register()` decorator automatically registers the agent
