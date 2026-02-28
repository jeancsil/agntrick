from agentic_framework.mcp.config import DEFAULT_MCP_SERVERS, get_mcp_servers_config


def test_get_mcp_servers_config_returns_copy(monkeypatch):
    resolved = get_mcp_servers_config()
    assert resolved.keys() == DEFAULT_MCP_SERVERS.keys()
    assert resolved is not DEFAULT_MCP_SERVERS


def test_get_mcp_servers_config_applies_override():
    resolved = get_mcp_servers_config(override={"new-server": {"transport": "sse", "url": "https://example.com"}})
    assert resolved["new-server"]["url"] == "https://example.com"
