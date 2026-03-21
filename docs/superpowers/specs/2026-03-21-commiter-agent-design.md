# CommitterAgent Design Spec

**Date:** 2026-03-21
**Author:** Design from brainstorming session
**Status:** Draft

## Overview

Create a `CommitterAgent` (spelled with double 't') that analyzes git changes and generates conventional commit messages. The agent will be accessible via CLI first, with WhatsApp integration through agntrick-whatsapp coming later.

**Note:** WhatsApp integration is out of scope for this initial implementation and will be added in a future update to agntrick-whatsapp.

## Purpose

The CommitterAgent helps developers:
1. Understand what changes are staged or modified
2. Get summaries of git changes
3. Generate conventional commit messages
4. View git history and specific commits

## Architecture

### Files to Create

```
src/agntrick/agents/committer.py        # New agent (spelled with double 't')
src/agntrick/tools/git_command.py       # Unified git tool
prompts/committer.md                    # System prompt
tests/test_committer_agent.py           # Tests (new)
tests/test_git_command_tool.py          # Tests (new)
```

### Files to Update

```
src/agntrick/tools/__init__.py          # Export git tools
src/agntrick/prompts.py                 # Add fallback prompt (optional)
```

## Components

### CommitterAgent

**Location:** `src/agntrick/agents/committer.py` (spelled with double 't')

**Responsibilities:**
- Extend `AgentBase`
- Register as `"committer"` in `AgentRegistry` (no MCP servers required)
- Provide system prompt for commit analysis
- Expose `GitCommandTool` as local tool

**Interface:**
```python
@AgentRegistry.register("committer")  # No MCP servers needed for git operations
class CommitterAgent(AgentBase):
    @property
    def system_prompt(self) -> str:
        return load_prompt("committer")

    def local_tools(self) -> Sequence[Any]:
        # Tool defaults to current directory, accepts optional repo_path
        return [GitCommandTool().to_langchain_tool()]
```

**MCP Registration:** No MCP servers required. All git operations are performed locally via subprocess.

### GitCommandTool

**Location:** `src/agntrick/tools/git_command.py`

**Responsibilities:**
- Execute git commands via subprocess
- Support multiple git operations
- Handle errors gracefully
- Return structured output
- Validate input to prevent command injection

**Supported Operations (whitelisted):**
| Command | Description |
|---------|-------------|
| `status` | Get git repository status |
| `diff` | Show unstaged changes |
| `diff --cached` | Show staged changes |
| `log` | Show commit history |
| `show <commit>` | Show specific commit details |
| `branch` | Show current branch |

**Interface:**
```python
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

**Security Considerations:**
- Only whitelisted git subcommands are allowed
- Uses `subprocess.run()` with list arguments (never `shell=True`)
- No arbitrary command execution
- 30-second timeout to prevent hanging

### System Prompt

**Location:** `prompts/committer.md`

**Content:**
- Define conventional commit format:
  - Format: `<type>(<scope>): <subject>`
  - Types: feat, fix, docs, refactor, style, test, chore, build, ci, perf, revert
  - Breaking changes: append `!` after type/scope or add `BREAKING CHANGE:` footer
  - Reference: https://www.conventionalcommits.org/
- Instructions for analyzing changes
- Guidelines for generating commit messages
- Personality: concise, helpful, commit-focused

## Data Flow

```
User: "what's staged and suggest a commit message?"
       ↓
CommitterAgent.run(input_data)
       ↓
Agent uses GitCommandTool:
  - git_command("status")
  - git_command("diff --cached")
       ↓
LLM analyzes changes:
  - Identifies files affected
  - Categorizes changes (feat, fix, docs, etc.)
  - Generates summary + commit message
       ↓
Returns formatted response with:
  - Summary of changes
  - Suggested commit message
  - Files affected
```

## Usage Examples

### CLI Usage

```bash
# Check what's staged
agntrick committer -i "what's staged?"

# Get commit message suggestion
agntrick committer -i "summarize changes and suggest commit message"

# View recent commits
agntrick committer -i "show last 5 commits"

# View specific commit
agntrick committer -i "show commit abc123"
```

### WhatsApp Usage (Future)

```
/committer what's staged?
/committer suggest commit message
/committer show recent history
```

**Note:** WhatsApp integration will be added in a future update to agntrick-whatsapp.

## Error Handling

| Scenario | Response |
|----------|----------|
| Not a git repository | "Error: Not a git repository. Please run this command in a git repository." |
| No staged changes | "No staged changes found. Use `git add <files>` to stage changes." |
| Git command fails | Return stderr with helpful context |
| Unsupported git command | "Error: Unsupported git command. Allowed: branch, diff, log, show, status" |
| Large diff output | Truncate after 500 lines with warning: "Output truncated (500+ lines). Use `git diff <file>` for specific files." |
| Invalid commit hash | "Error: Commit 'xyz' not found." |
| Command timeout | "Error: Git command timed out (30s)." |

**Diff Truncation Policy:**
- Truncate after 500 lines
- Suggest using `git diff --stat` for overview
- Suggest using `git diff <file>` for specific files

## Testing

### Unit Tests (`tests/test_git_command_tool.py`)

```python
class TestGitCommandTool:
    """Tests for GitCommandTool."""

    def test_status_returns_output(self, monkeypatch):
        """Test git status returns output."""
        ...

    def test_diff_returns_staged_changes(self, monkeypatch):
        """Test git diff --cached shows staged changes."""
        ...

    def test_log_shows_commit_history(self, monkeypatch):
        """Test git log shows commit history."""
        ...

    def test_error_not_git_repository(self, monkeypatch):
        """Test error when not in a git repository."""
        ...

    def test_unsupported_command_rejected(self):
        """Test unsupported commands return error."""
        ...

    def test_command_timeout(self, monkeypatch):
        """Test timeout handling."""
        ...
```

**Test Coverage:**
- Each git command (status, diff, log, show, branch)
- Mock subprocess calls
- Error handling (not a repo, timeout, unsupported command)
- Output parsing and truncation

### Integration Tests (`tests/test_committer_agent.py`)

```python
class TestCommitterAgent:
    """Tests for CommitterAgent."""

    def test_agent_is_registered(self):
        """Test agent is registered in AgentRegistry."""
        ...

    def test_system_prompt_loaded(self):
        """Test system prompt is loaded correctly."""
        ...

    def test_staged_changes_summary(self, monkeypatch):
        """Test agent summarizes staged changes."""
        ...

    def test_suggests_commit_message(self, monkeypatch):
        """Test agent generates commit message suggestions."""
        ...

    def test_no_changes_helpful_response(self, monkeypatch):
        """Test agent provides help when no changes exist."""
        ...

    def test_view_commit_history(self, monkeypatch):
        """Test agent shows commit history."""
        ...
```

**Test Scenarios:**
- Staged changes only
- Mixed staged/unstaged
- No changes
- View history
- View specific commit
- Mock git tool output
- Verify LLM response structure

## Dependencies

**No new external dependencies** - uses Python standard library:
- `subprocess` for git commands
- `pathlib` for path handling

## Future Enhancements

1. **WhatsApp integration** (agntrick-whatsapp):
   - Add `/committer` command support
   - Enable use via WhatsApp messages

2. **Remote integration** (later):
   - GitHub PR/MR support
   - GitLab merge request support

3. **Advanced features** (later):
   - Commit message linting
   - Branch comparison
   - Interactive staging suggestions

## Implementation Checklist

- [ ] Create `GitCommandTool` class (`src/agntrick/tools/git_command.py`)
- [ ] Create `CommitterAgent` class (`src/agntrick/agents/committer.py`)
- [ ] Create system prompt (`prompts/committer.md`)
- [ ] Update `src/agntrick/tools/__init__.py`:
  ```python
  from .git_command import GitCommandTool

  __all__ = [
      # ... existing exports ...
      "GitCommandTool",
  ]
  ```
- [ ] Add unit tests (`tests/test_git_command_tool.py`)
- [ ] Add integration tests (`tests/test_committer_agent.py`)
- [ ] Run `make check` and fix any issues
- [ ] Run `make test` and ensure coverage maintained (80%+)
- [ ] Update README.md with new agent

## Success Criteria

- [ ] Agent runs via CLI: `agntrick committer -i "help"`
- [ ] Agent shows git status
- [ ] Agent shows staged changes
- [ ] Agent generates commit message suggestions
- [ ] Agent shows commit history
- [ ] All tests pass (80%+ coverage maintained)
- [ ] `make check` passes with no errors
