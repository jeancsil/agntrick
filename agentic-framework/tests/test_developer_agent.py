import asyncio
from types import SimpleNamespace

from agentic_framework.core.developer_agent import DeveloperAgent


class DummyGraph:
    async def ainvoke(self, payload, config):
        return {"messages": [SimpleNamespace(content="done")]}


def test_developer_agent_system_prompt(monkeypatch):
    monkeypatch.setattr("agentic_framework.core.langgraph_agent.ChatOpenAI", lambda **kwargs: object())
    monkeypatch.setattr("agentic_framework.core.langgraph_agent.create_agent", lambda **kwargs: DummyGraph())

    agent = DeveloperAgent(initial_mcp_tools=[])

    assert "Principal Software Engineer" in agent.system_prompt
    assert "discover_structure" in agent.system_prompt
    assert "find_files" in agent.system_prompt
    assert "get_file_outline" in agent.system_prompt
    assert "read_file_fragment" in agent.system_prompt
    assert "code_search" in agent.system_prompt
    assert "edit_file" in agent.system_prompt


def test_developer_agent_local_tools_count(monkeypatch):
    monkeypatch.setattr("agentic_framework.core.langgraph_agent.ChatOpenAI", lambda **kwargs: object())
    monkeypatch.setattr("agentic_framework.core.langgraph_agent.create_agent", lambda **kwargs: DummyGraph())

    agent = DeveloperAgent(initial_mcp_tools=[])

    tools = agent.get_tools()
    assert len(tools) == 6

    tool_names = {tool.name for tool in tools}
    expected_names = {
        "discover_structure",
        "find_files",
        "get_file_outline",
        "read_file_fragment",
        "code_search",
        "edit_file",
    }
    assert tool_names == expected_names


def test_developer_agent_tool_descriptions(monkeypatch):
    monkeypatch.setattr("agentic_framework.core.langgraph_agent.ChatOpenAI", lambda **kwargs: object())
    monkeypatch.setattr("agentic_framework.core.langgraph_agent.create_agent", lambda **kwargs: DummyGraph())

    agent = DeveloperAgent(initial_mcp_tools=[])

    tools = agent.get_tools()
    tools_by_name = {tool.name: tool for tool in tools}

    assert "files and directories recursively" in tools_by_name["discover_structure"].description.lower()
    assert "file search by name" in tools_by_name["find_files"].description.lower()
    outline_desc = tools_by_name["get_file_outline"].description.lower()
    assert "class" in outline_desc and "function" in outline_desc
    assert "specific line range" in tools_by_name["read_file_fragment"].description.lower()
    assert "ripgrep" in tools_by_name["code_search"].description.lower()
    assert "line-based operations" in tools_by_name["edit_file"].description.lower()


def test_developer_agent_run(monkeypatch):
    monkeypatch.setattr("agentic_framework.core.langgraph_agent.ChatOpenAI", lambda **kwargs: object())
    monkeypatch.setattr("agentic_framework.core.langgraph_agent.create_agent", lambda **kwargs: DummyGraph())

    agent = DeveloperAgent(initial_mcp_tools=[])

    result = asyncio.run(agent.run("Find all files related to agents"))
    assert result == "done"


def test_developer_agent_with_mcp_tools(monkeypatch):
    monkeypatch.setattr("agentic_framework.core.langgraph_agent.ChatOpenAI", lambda **kwargs: object())
    monkeypatch.setattr("agentic_framework.core.langgraph_agent.create_agent", lambda **kwargs: DummyGraph())

    # Simulate MCP tools
    class MockMCPTool:
        name = "webfetch"
        description = "Fetch web content"

    agent = DeveloperAgent(initial_mcp_tools=[MockMCPTool()])

    # MCP tools are added during initialization (_ensure_initialized is called during run)
    # We can verify the agent was initialized with MCP tools
    assert agent._initial_mcp_tools is not None
    assert len(agent._initial_mcp_tools) == 1
    assert agent._initial_mcp_tools[0].name == "webfetch"

    # After running, tools should include both local and MCP tools
    asyncio.run(agent.run("test"))
    tools = agent.get_tools()

    # Should have 6 local tools + 1 MCP tool
    assert len(tools) == 7
    tool_names = {tool.name for tool in tools}
    assert "webfetch" in tool_names
