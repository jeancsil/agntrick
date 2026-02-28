# Plan: Production-Grade File Editing for AI Agents

## Problem Statement

The DeveloperAgent makes incorrect edits that corrupt files:
1. Edits at wrong line numbers (doesn't read first)
2. Removes syntax elements like quotes (doesn't copy exactly)
3. Ignores SYNTAX WARNING output (no self-correction)

## Root Cause Analysis

1. **Agent doesn't read before editing** - It guesses line numbers
2. **Tool output doesn't guide correction** - Warnings are shown but not actionable
3. **No enforcement of workflow** - Agent can skip the read step
4. **Line-number-only editing is fragile** - Small changes break line calculations

## Implementation Plan

### Phase 1: Update System Prompt (P0 - Critical, Low Effort)

**File**: `src/agentic_framework/core/developer_agent.py`

Add explicit read-first workflow instructions to the system prompt:

```python
@property
def system_prompt(self) -> str:
    return """You are a software engineer assistant with codebase exploration and editing capabilities.

## AVAILABLE TOOLS

1. **find_files** - Fast file search by name using fd
2. **discover_structure** - Directory tree exploration
3. **get_file_outline** - Extract class/function signatures (multi-language)
4. **read_file_fragment** - Read specific line ranges
5. **code_search** - Fast pattern search via ripgrep
6. **edit_file** - Edit files with line-based operations
7. **webfetch** (MCP) - Fetch web content

## MANDATORY FILE EDITING WORKFLOW

Before using edit_file, you MUST follow this sequence:

### Step 1: READ FIRST (Required)
- Use `read_file_fragment` to see the EXACT lines you plan to modify
- Never guess line numbers - always verify them
- Example: `read_file_fragment("example.py:88:95")`

### Step 2: COPY EXACTLY
When providing replacement content:
- Copy the exact text including all quotes, indentation, and punctuation
- Do NOT truncate, paraphrase, or summarize
- Preserve docstring delimiters (`"""` or `'''`)
- Maintain exact indentation (tabs vs spaces)

### Step 3: APPLY EDIT
Use edit_file with precise parameters:
- Colon format: `replace:path:start:end:content`
- JSON format for complex content: `{"op": "replace", "path": "...", "start": N, "end": N, "content": "..."}`

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
4. Maximum 3 retries per edit

## EDIT_FILE OPERATIONS

- `replace:path:start:end:content` - Replace lines start to end (1-indexed)
- `insert:path:after_line:content` - Insert after line number
- `insert:path:before_line:content` - Insert before line number
- `delete:path:start:end` - Delete lines start to end

## IMPORTANT REMINDERS

- Line numbers are 1-indexed
- Content uses `\\n` for newlines in colon format
- Always read before editing - NO EXCEPTIONS
- You also have access to MCP tools like `webfetch` if you need to fetch information from the web

Always provide clear, concise explanations and suggest improvements when relevant.
"""
```

---

### Phase 2: Add SEARCH/REPLACE Operation (P1 - High Impact, Medium Effort)

**File**: `src/agentic_framework/tools/codebase_explorer.py`

Add a new operation type that finds and replaces exact text (more robust than line numbers):

```python
def _handle_json_input(self, input_str: str) -> Any:
    """Handle JSON-formatted input for complex content."""
    import json

    data = json.loads(input_str)
    op = data.get("op")
    path = data.get("path")
    content = data.get("content", "")

    if op == "replace":
        return self._replace_lines(path, data["start"], data["end"], content)
    elif op == "search_replace":
        return self._search_replace(path, data["old"], data.get("new", ""))
    elif op == "insert":
        return self._insert_lines(path, data.get("after"), data.get("before"), content)
    elif op == "delete":
        return self._delete_lines(path, data["start"], data["end"])
    else:
        return f"Error: Unknown operation '{op}'"

def _search_replace(self, path: str, old_text: str, new_text: str) -> str:
    """Find and replace exact text in file.

    More robust than line-based editing because it doesn't require line numbers.
    Fails if old_text is not found or found multiple times.
    """
    full_path = self._validate_path(path)

    if not full_path.exists():
        return f"Error: File '{path}' not found"

    warning = self._check_file_size(full_path)

    try:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        return f"Error: File '{path}' is not valid UTF-8 text"

    # Count matches
    count = content.count(old_text)

    if count == 0:
        # Try fuzzy match (strip trailing whitespace differences)
        old_normalized = old_text.rstrip()
        matches = [i for i in range(len(content)) if content[i:i+len(old_normalized)].rstrip() == old_normalized]
        if len(matches) == 1:
            # Found with fuzzy match, use it
            count = 1
        else:
            return self._format_search_error(content, old_text)

    if count > 1:
        return f"Error: Found {count} occurrences of the search text in '{path}'. " \
               f"Make the search text more specific (include more context lines)."

    # Perform replacement
    new_content = content.replace(old_text, new_text, 1)

    self._atomic_write(full_path, new_content)

    # Find line numbers for reporting
    lines_before = content[:content.index(old_text)].count('\n') + 1
    lines_after = old_text.count('\n')
    end_line = lines_before + lines_after

    result = f"Replaced text at lines {lines_before}-{end_line} in '{path}'"
    if warning:
        result = f"{warning}\n{result}"

    # Validate syntax after edit
    syntax_warning = self._validate_syntax(new_content, path)
    if syntax_warning:
        result = f"{result}{syntax_warning}"

    return result

def _format_search_error(self, content: str, old_text: str) -> str:
    """Format helpful error message when search text not found."""
    # Try to find similar text
    old_lines = old_text.strip().split('\n')
    if old_lines:
        first_line = old_lines[0].strip()
        for i, line in enumerate(content.split('\n'), 1):
            if first_line in line:
                return (
                    f"Error: Search text not found exactly.\n"
                    f"Found similar text at line {i}: {line.strip()[:50]}...\n"
                    f"Tip: Use read_file_fragment to see the exact content."
                )

    return (
        f"Error: Search text not found in file.\n"
        f"Tip: Use read_file_fragment to view the file content first, "
        f"then copy the exact text to replace."
    )
```

Update the description property:

```python
@property
def description(self) -> str:
    return """Edit files with line-based or text-based operations.

Operations:
- replace:path:start:end:content - Replace lines start to end
- insert:path:after_line:content - Insert after line number
- insert:path:before_line:content - Insert before line number
- delete:path:start:end - Delete lines start to end

For complex content with colons/newlines, use JSON:
{"op": "replace", "path": "...", "start": N, "end": N, "content": "..."}

RECOMMENDED: Use search_replace for precise edits (no line numbers needed):
{"op": "search_replace", "path": "...", "old": "exact text to find", "new": "replacement text"}

Line numbers are 1-indexed. Content uses \\n for newlines.
ALWAYS read the file first using read_file_fragment to verify content before editing.
"""
```

---

### Phase 3: Enhance Error Messages (P2 - Medium Effort, Medium Impact)

**File**: `src/agentic_framework/tools/codebase_explorer.py`

Add structured error types and suggested actions:

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class EditError:
    """Structured error information for edit operations."""
    error_type: str
    message: str
    suggested_action: str
    context: dict

    def __str__(self) -> str:
        return f"""Error ({self.error_type}): {self.message}

Suggested action: {self.suggested_action}
Context: {self.context}
"""

# Update validation methods to use structured errors
def _validate_line_bounds(self, lines: List[str], start: int, end: int) -> None:
    """Validate line numbers are within bounds. Raises ValueError with helpful message."""
    total_lines = len(lines)

    if start < 1:
        raise ValueError(f"Start line must be >= 1, got {start}. Line numbers are 1-indexed.")
    if end < start:
        raise ValueError(f"End line ({end}) must be >= start line ({start}).")
    if start > total_lines:
        raise ValueError(
            f"Start line ({start}) exceeds file length ({total_lines}). "
            f"Use read_file_fragment to verify line numbers before editing."
        )
    if end > total_lines + 1:
        raise ValueError(
            f"End line ({end}) exceeds file length + 1 ({total_lines + 1}). "
            f"Use read_file_fragment to verify line numbers before editing."
        )
```

---

### Phase 4: Add Verify Edit Tool (P3 - Optional)

**File**: `src/agentic_framework/tools/codebase_explorer.py`

```python
class VerifyEditTool(CodebaseExplorer, Tool):
    """Tool to verify recent edits by reading back and checking syntax."""

    @property
    def name(self) -> str:
        return "verify_edit"

    @property
    def description(self) -> str:
        return """Verify an edit by reading affected lines and checking syntax.
        Input: 'path:start:end' of the edited region.
        Returns: Current content and syntax validation result.
        Use this after every edit to confirm changes were applied correctly.
        """

    def invoke(self, input_str: str) -> str:
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

            content = "".join(lines[max(0, start_line - 1):end_line])

            # Validate syntax
            from agentic_framework.tools.syntax_validator import get_validator
            result = get_validator().validate("".join(lines), file_path)

            output = [f"Lines {start_line}-{end_line} in '{file_path}':", "", content]

            if result.skipped:
                output.append(f"\n(Syntax check skipped: {result.skip_reason})")
            elif not result.is_valid:
                output.append(f"\nSYNTAX WARNING:{result.warning_message}")
            else:
                output.append("\n✓ Syntax validation passed")

            return "\n".join(output)

        except Exception as e:
            return f"Error: {e}"
```

---

## Testing Plan

### Unit Tests

1. Test search_replace with exact match
2. Test search_replace with no match (error message)
3. Test search_replace with multiple matches (error message)
4. Test fuzzy matching for whitespace differences
5. Test system prompt contains read-first instructions
6. Test verify_edit tool

### Integration Tests

1. Test agent workflow: read → edit → verify
2. Test error recovery: agent sees error, reads file, retries
3. Test syntax warning triggers verification

### Manual Testing

```bash
# Test 1: Simple text replacement
uv --directory agentic-framework run agentic-run developer -i "Use search_replace to change 'A mock weather tool.' to 'A mock weather tool for testing.' in example.py"

# Test 2: Complex edit with verification
uv --directory agentic-framework run agentic-run developer -i "Update the CalculatorTool docstring to mention it also supports abs, round, min, max, sum functions"

# Test 3: Error recovery
uv --directory agentic-framework run agentic-run developer -i "Replace a non-existent string in example.py"
```

---

## Validation Checklist

- [x] System prompt updated with read-first workflow
- [x] search_replace operation implemented
- [x] Error messages include suggested actions
- [x] Unit tests pass (133 tests)
- [x] make check passes
- [x] make test passes
- [ ] Manual testing successful (run developer agent test)

---

## Rollback Plan

If issues arise:
1. Revert system prompt changes (single commit)
2. Disable search_replace by removing from _handle_json_input
3. Fall back to line-based editing only

---

## Dependencies

- tree-sitter==0.21.3 (already pinned)
- tree-sitter-languages>=1.10.2 (already installed)

---

## Estimated Effort

| Phase | Effort | Risk |
|-------|--------|------|
| Phase 1: System Prompt | 30 min | Low |
| Phase 2: SEARCH/REPLACE | 2 hours | Medium |
| Phase 3: Error Messages | 1 hour | Low |
| Phase 4: Verify Tool | 1 hour | Low |
| Testing | 2 hours | Low |
| **Total** | **6.5 hours** | Medium |
