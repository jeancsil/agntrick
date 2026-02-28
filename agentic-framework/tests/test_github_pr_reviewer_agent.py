"""Tests for the GitHub PR Reviewer agent."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from agentic_framework.core.github_pr_reviewer import (
    GitHubPRReviewerAgent,
    get_pr_comments,
    get_pr_diff,
    get_pr_metadata,
    post_general_comment,
    post_review_comment,
    reply_to_review_comment,
)


class DummyGraph:
    async def ainvoke(self, payload: dict, config: dict) -> dict:
        return {"messages": [SimpleNamespace(content="done")]}


# ---------------------------------------------------------------------------
# Agent-level tests
# ---------------------------------------------------------------------------


def test_github_pr_reviewer_system_prompt(monkeypatch: object) -> None:
    monkeypatch.setattr("agentic_framework.core.langgraph_agent.ChatOpenAI", lambda **kwargs: object())  # type: ignore[attr-defined]
    monkeypatch.setattr("agentic_framework.core.langgraph_agent.create_agent", lambda **kwargs: DummyGraph())  # type: ignore[attr-defined]

    agent = GitHubPRReviewerAgent(initial_mcp_tools=[])

    assert "expert code reviewer" in agent.system_prompt.lower()
    assert "get_pr_metadata" in agent.system_prompt
    assert "get_pr_diff" in agent.system_prompt
    assert "post_review_comment" in agent.system_prompt
    assert "post_general_comment" in agent.system_prompt
    assert "get_pr_comments" in agent.system_prompt
    assert "reply_to_review_comment" in agent.system_prompt


def test_github_pr_reviewer_tools_count(monkeypatch: object) -> None:
    monkeypatch.setattr("agentic_framework.core.langgraph_agent.ChatOpenAI", lambda **kwargs: object())  # type: ignore[attr-defined]
    monkeypatch.setattr("agentic_framework.core.langgraph_agent.create_agent", lambda **kwargs: DummyGraph())  # type: ignore[attr-defined]

    agent = GitHubPRReviewerAgent(initial_mcp_tools=[])

    tools = agent.get_tools()
    assert len(tools) == 6

    tool_names = {tool.name for tool in tools}
    expected = {
        "get_pr_diff",
        "get_pr_comments",
        "post_review_comment",
        "post_general_comment",
        "reply_to_review_comment",
        "get_pr_metadata",
    }
    assert tool_names == expected


def test_github_pr_reviewer_tool_descriptions(monkeypatch: object) -> None:
    monkeypatch.setattr("agentic_framework.core.langgraph_agent.ChatOpenAI", lambda **kwargs: object())  # type: ignore[attr-defined]
    monkeypatch.setattr("agentic_framework.core.langgraph_agent.create_agent", lambda **kwargs: DummyGraph())  # type: ignore[attr-defined]

    agent = GitHubPRReviewerAgent(initial_mcp_tools=[])
    tools_by_name = {t.name: t for t in agent.get_tools()}

    assert "head sha" in tools_by_name["get_pr_metadata"].description.lower()
    assert "diff" in tools_by_name["get_pr_diff"].description.lower()
    assert "comment" in tools_by_name["get_pr_comments"].description.lower()
    assert "inline" in tools_by_name["post_review_comment"].description.lower()
    assert "top-level" in tools_by_name["post_general_comment"].description.lower()
    assert "reply" in tools_by_name["reply_to_review_comment"].description.lower()


def test_github_pr_reviewer_run(monkeypatch: object) -> None:
    monkeypatch.setattr("agentic_framework.core.langgraph_agent.ChatOpenAI", lambda **kwargs: object())  # type: ignore[attr-defined]
    monkeypatch.setattr("agentic_framework.core.langgraph_agent.create_agent", lambda **kwargs: DummyGraph())  # type: ignore[attr-defined]

    agent = GitHubPRReviewerAgent(initial_mcp_tools=[])
    result = asyncio.run(agent.run("Review PR #42 in owner/repo"))
    assert result == "done"


# ---------------------------------------------------------------------------
# Missing-token tests (all 6 tools)
# ---------------------------------------------------------------------------


def test_get_pr_diff_missing_token(monkeypatch: object) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)  # type: ignore[attr-defined]
    result = get_pr_diff("owner/repo", 42)
    assert "Error" in result
    assert "GITHUB_TOKEN" in result


def test_get_pr_comments_missing_token(monkeypatch: object) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)  # type: ignore[attr-defined]
    result = get_pr_comments("owner/repo", 42)
    assert "Error" in result
    assert "GITHUB_TOKEN" in result


def test_post_review_comment_missing_token(monkeypatch: object) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)  # type: ignore[attr-defined]
    result = post_review_comment("owner/repo", 42, "abc123", "file.py", 10, "body")
    assert "Error" in result
    assert "GITHUB_TOKEN" in result


def test_post_general_comment_missing_token(monkeypatch: object) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)  # type: ignore[attr-defined]
    result = post_general_comment("owner/repo", 42, "body")
    assert "Error" in result
    assert "GITHUB_TOKEN" in result


def test_reply_to_review_comment_missing_token(monkeypatch: object) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)  # type: ignore[attr-defined]
    result = reply_to_review_comment("owner/repo", 42, 100, "reply")
    assert "Error" in result
    assert "GITHUB_TOKEN" in result


def test_get_pr_metadata_missing_token(monkeypatch: object) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)  # type: ignore[attr-defined]
    result = get_pr_metadata("owner/repo", 42)
    assert "Error" in result
    assert "GITHUB_TOKEN" in result


# ---------------------------------------------------------------------------
# API-error tests
# ---------------------------------------------------------------------------


def test_get_pr_diff_api_error(monkeypatch: object) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")  # type: ignore[attr-defined]
    with patch("agentic_framework.core.github_pr_reviewer.requests.get", side_effect=Exception("timeout")):
        result = get_pr_diff("owner/repo", 42)
    assert "Error" in result
    assert "timeout" in result


def test_get_pr_comments_api_error(monkeypatch: object) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")  # type: ignore[attr-defined]
    with patch("agentic_framework.core.github_pr_reviewer.requests.get", side_effect=Exception("503")):
        result = get_pr_comments("owner/repo", 42)
    assert "Error" in result


def test_post_review_comment_api_error(monkeypatch: object) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")  # type: ignore[attr-defined]
    with patch("agentic_framework.core.github_pr_reviewer.requests.post", side_effect=Exception("422")):
        result = post_review_comment("owner/repo", 42, "abc", "file.py", 5, "comment")
    assert "Error" in result


def test_post_general_comment_api_error(monkeypatch: object) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")  # type: ignore[attr-defined]
    with patch("agentic_framework.core.github_pr_reviewer.requests.post", side_effect=Exception("403")):
        result = post_general_comment("owner/repo", 42, "summary")
    assert "Error" in result


def test_reply_to_review_comment_api_error(monkeypatch: object) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")  # type: ignore[attr-defined]
    with patch("agentic_framework.core.github_pr_reviewer.requests.post", side_effect=Exception("404")):
        result = reply_to_review_comment("owner/repo", 42, 999, "reply")
    assert "Error" in result


def test_get_pr_metadata_api_error(monkeypatch: object) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")  # type: ignore[attr-defined]
    with patch("agentic_framework.core.github_pr_reviewer.requests.get", side_effect=Exception("not found")):
        result = get_pr_metadata("owner/repo", 42)
    assert "Error" in result


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


def test_get_pr_diff_success(monkeypatch: object) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")  # type: ignore[attr-defined]

    mock_response = MagicMock()
    mock_response.json.return_value = [
        {
            "filename": "src/main.py",
            "status": "modified",
            "additions": 5,
            "deletions": 2,
            "patch": "@@ -1,3 +1,6 @@\n+new line",
        }
    ]
    mock_response.raise_for_status = MagicMock()

    with patch("agentic_framework.core.github_pr_reviewer.requests.get", return_value=mock_response):
        result = get_pr_diff("owner/repo", 42)

    assert "src/main.py" in result
    assert "modified" in result
    assert "+5/-2" in result
    assert "@@ -1,3" in result


def test_get_pr_diff_no_patch(monkeypatch: object) -> None:
    """Files without a patch (e.g. binary files) should not crash."""
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")  # type: ignore[attr-defined]

    mock_response = MagicMock()
    mock_response.json.return_value = [
        {
            "filename": "image.png",
            "status": "added",
            "additions": 0,
            "deletions": 0,
        }
    ]
    mock_response.raise_for_status = MagicMock()

    with patch("agentic_framework.core.github_pr_reviewer.requests.get", return_value=mock_response):
        result = get_pr_diff("owner/repo", 42)

    assert "image.png" in result
    assert "added" in result


def test_get_pr_comments_with_both_types(monkeypatch: object) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")  # type: ignore[attr-defined]

    review_response = MagicMock()
    review_response.raise_for_status = MagicMock()
    review_response.json.return_value = [
        {
            "id": 1,
            "user": {"login": "reviewer"},
            "path": "src/main.py",
            "line": 10,
            "body": "Consider extracting this into a function",
        }
    ]

    issue_response = MagicMock()
    issue_response.raise_for_status = MagicMock()
    issue_response.json.return_value = [
        {
            "id": 2,
            "user": {"login": "author"},
            "body": "Thanks for the review!",
        }
    ]

    with patch(
        "agentic_framework.core.github_pr_reviewer.requests.get",
        side_effect=[review_response, issue_response],
    ):
        result = get_pr_comments("owner/repo", 42)

    assert "reviewer" in result
    assert "src/main.py" in result
    assert "Consider extracting" in result
    assert "author" in result
    assert "Thanks for the review" in result


def test_get_pr_comments_empty(monkeypatch: object) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")  # type: ignore[attr-defined]

    empty_response = MagicMock()
    empty_response.raise_for_status = MagicMock()
    empty_response.json.return_value = []

    with patch(
        "agentic_framework.core.github_pr_reviewer.requests.get",
        side_effect=[empty_response, empty_response],
    ):
        result = get_pr_comments("owner/repo", 42)

    assert "None" in result


def test_post_review_comment_success(monkeypatch: object) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")  # type: ignore[attr-defined]

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"html_url": "https://github.com/owner/repo/pull/42#discussion_r1"}

    with patch("agentic_framework.core.github_pr_reviewer.requests.post", return_value=mock_response):
        result = post_review_comment("owner/repo", 42, "abc123", "src/main.py", 10, "Bug here")

    assert "src/main.py" in result
    assert "10" in result
    assert "https://github.com" in result


def test_post_general_comment_success(monkeypatch: object) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")  # type: ignore[attr-defined]

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"html_url": "https://github.com/owner/repo/pull/42#issuecomment-1"}

    with patch("agentic_framework.core.github_pr_reviewer.requests.post", return_value=mock_response):
        result = post_general_comment("owner/repo", 42, "Great PR!")

    assert "PR #42" in result
    assert "https://github.com" in result


def test_reply_to_review_comment_success(monkeypatch: object) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")  # type: ignore[attr-defined]

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"html_url": "https://github.com/owner/repo/pull/42#discussion_r2"}

    with patch("agentic_framework.core.github_pr_reviewer.requests.post", return_value=mock_response):
        result = reply_to_review_comment("owner/repo", 42, 100, "Thanks for the feedback!")

    assert "100" in result
    assert "https://github.com" in result


def test_get_pr_metadata_success(monkeypatch: object) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")  # type: ignore[attr-defined]

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "title": "Add feature X",
        "body": "This PR adds feature X",
        "user": {"login": "contributor"},
        "state": "open",
        "base": {"ref": "main"},
        "head": {"ref": "feature-x", "sha": "abc123def456"},
        "changed_files": 3,
        "additions": 50,
        "deletions": 10,
    }

    with patch("agentic_framework.core.github_pr_reviewer.requests.get", return_value=mock_response):
        result = get_pr_metadata("owner/repo", 42)

    assert "Add feature X" in result
    assert "contributor" in result
    assert "abc123def456" in result
    assert "main" in result
    assert "+50/-10" in result
    assert "This PR adds feature X" in result


# ---------------------------------------------------------------------------
# Retry logic tests
# ---------------------------------------------------------------------------


def test_get_pr_diff_retries_on_429_and_succeeds(monkeypatch: object) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")  # type: ignore[attr-defined]

    rate_limited = MagicMock()
    rate_limited.status_code = 429

    success = MagicMock()
    success.status_code = 200
    success.raise_for_status = MagicMock()
    success.json.return_value = []

    with patch(
        "agentic_framework.core.github_pr_reviewer.requests.get",
        side_effect=[rate_limited, success],
    ):
        with patch("agentic_framework.core.github_pr_reviewer.time.sleep") as mock_sleep:
            result = get_pr_diff("owner/repo", 42)

    mock_sleep.assert_called_once_with(1)  # 2**0 = 1s first backoff
    assert "Error" not in result
    assert "0 file(s)" in result


def test_post_general_comment_retries_on_503(monkeypatch: object) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")  # type: ignore[attr-defined]

    unavailable = MagicMock()
    unavailable.status_code = 503

    success = MagicMock()
    success.status_code = 200
    success.raise_for_status = MagicMock()
    success.json.return_value = {"html_url": "https://github.com/owner/repo/pull/1#issuecomment-1"}

    with patch(
        "agentic_framework.core.github_pr_reviewer.requests.post",
        side_effect=[unavailable, success],
    ):
        with patch("agentic_framework.core.github_pr_reviewer.time.sleep") as mock_sleep:
            result = post_general_comment("owner/repo", 1, "summary")

    mock_sleep.assert_called_once_with(1)
    assert "Error" not in result
    assert "https://github.com" in result


# ---------------------------------------------------------------------------
# Line-number validation tests
# ---------------------------------------------------------------------------


def test_post_review_comment_rejects_zero_line(monkeypatch: object) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")  # type: ignore[attr-defined]
    result = post_review_comment("owner/repo", 42, "abc123", "file.py", 0, "comment")
    assert "Error" in result
    assert "positive integer" in result


def test_post_review_comment_rejects_negative_line(monkeypatch: object) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")  # type: ignore[attr-defined]
    result = post_review_comment("owner/repo", 42, "abc123", "file.py", -5, "comment")
    assert "Error" in result
    assert "positive integer" in result


def test_get_pr_metadata_null_body(monkeypatch: object) -> None:
    """PR with null body should not crash."""
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")  # type: ignore[attr-defined]

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "title": "Quick fix",
        "body": None,
        "user": {"login": "dev"},
        "state": "open",
        "base": {"ref": "main"},
        "head": {"ref": "fix", "sha": "deadbeef"},
        "changed_files": 1,
        "additions": 2,
        "deletions": 1,
    }

    with patch("agentic_framework.core.github_pr_reviewer.requests.get", return_value=mock_response):
        result = get_pr_metadata("owner/repo", 42)

    assert "Quick fix" in result
    assert "deadbeef" in result
