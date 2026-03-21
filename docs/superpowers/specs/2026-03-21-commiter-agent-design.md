# CommitterAgent Design Spec

**Date:** 2026-03-21
**Author:** Design from brainstorming session
**Status:** Draft

## Overview

Create a `CommitterAgent` that analyzes git changes and generates conventional commit messages. The agent will be accessible via CLI and WhatsApp (through agntrick-whatsapp).

## Purpose

The CommitterAgent helps developers:
1. Understand what changes are staged or modified
2. Get summaries of git changes
3. Generate conventional commit messages
4. View git history and specific commits

## Architecture

### Files to Create

```
src/agntrick/agents/commiter.py         # New agent
src/agntrick/tools/git_command.py       # Unified git tool
prompts/commiter.md                     # System prompt
```

### Files to Update

```
src/agntrick/tools/__init__.py          # Export git tools
tests/test_commiter_agent.py            # Tests (new)
tests/test_git_command_tool.py          # Tests (new)
```

## Components

### CommitterAgent

**Location:** `src/agntrick/agents/commiter.py`

**Responsibilities:**
- Extend `AgentBase`
- Register as `"commiter"` in `AgentRegistry`
- Provide system prompt for commit analysis
- Expose `GitCommandTool` as local tool

**Interface:**
```python
@AgentRegistry.register("commiter")
class CommitterAgent(AgentBase):
    @property
    def system_prompt(self) -> str:
        return load_prompt("commiter")

    def local_tools(self) -> Sequence[Any]:
        return [GitCommandTool(str(Path.cwd())).to_langchain_tool()]
```

### GitCommandTool

**Location:** `src/agntrick/tools/git_command.py`

**Responsibilities:**
- Execute git commands via subprocess
- Support multiple git operations
- Handle errors gracefully
- Return structured output

**Supported Operations:**
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
    name = "git_command"
    description = "Execute git commands to analyze repository changes"

    def invoke(self, input_str: str) -> str:
        """Execute a git command.

        Args:
            input_str: Git command (e.g., "status", "diff --cached", "log -5")

        Returns:
            Command output or error message
        """
```

### System Prompt

**Location:** `prompts/commiter.md`

**Content:**
- Define conventional commit format (feat, fix, docs, refactor, style, test, chore)
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
agntrick commiter -i "what's staged?"

# Get commit message suggestion
agntrick commiter -i "summarize changes and suggest commit message"

# View recent commits
agntrick commiter -i "show last 5 commits"

# View specific commit
agntrick commiter -i "show commit abc123"
```

### WhatsApp Usage

```
/commiter what's staged?
/commiter suggest commit message
/commiter show recent history
```

## Error Handling

| Scenario | Response |
|----------|----------|
| Not a git repository | "Error: Not a git repository. Please run this command in a git repository." |
| No staged changes | "No staged changes found. Use `git add <files>` to stage changes." |
| Git command fails | Return stderr with helpful context |
| Large diff output | Truncate with warning: "Output truncated due to size. Use specific file paths for detailed diffs." |
| Invalid commit hash | "Error: Commit 'xyz' not found." |

## Testing

### Unit Tests (`tests/test_git_command_tool.py`)

- Test each git command (status, diff, log, show, branch)
- Mock subprocess calls
- Test error handling
- Test output parsing

### Integration Tests (`tests/test_commiter_agent.py`)

- Test agent with different scenarios:
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

1. **Remote integration** (later):
   - GitHub PR/MR support
   - GitLab merge request support

2. **Advanced features** (later):
   - Commit message linting
   - Branch comparison
   - Interactive staging suggestions

## Implementation Checklist

- [ ] Create `GitCommandTool` class
- [ ] Create `CommitterAgent` class
- [ ] Create `prompts/commiter.md`
- [ ] Update `tools/__init__.py`
- [ ] Add unit tests for `GitCommandTool`
- [ ] Add integration tests for `CommitterAgent`
- [ ] Run `make check` and fix any issues
- [ ] Run `make test` and ensure coverage maintained
- [ ] Update README.md with new agent

## Success Criteria

- [ ] Agent runs via CLI: `agntrick commiter -i "help"`
- [ ] Agent shows git status
- [ ] Agent shows staged changes
- [ ] Agent generates commit message suggestions
- [ ] Agent shows commit history
- [ ] All tests pass (80%+ coverage maintained)
- [ ] `make check` passes with no errors
