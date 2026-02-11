from agentic_framework.mcp.config import DEFAULT_MCP_SERVERS, get_mcp_servers_config


def test_get_mcp_servers_config_returns_copy(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("TINYFISH_API_KEY", raising=False)

    resolved = get_mcp_servers_config()
    assert resolved.keys() == DEFAULT_MCP_SERVERS.keys()
    assert resolved is not DEFAULT_MCP_SERVERS
    assert resolved["tavily"]["url"] == DEFAULT_MCP_SERVERS["tavily"]["url"]


def test_get_mcp_servers_config_resolves_tavily_api_key(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "secret")

    resolved = get_mcp_servers_config()
    assert "tavilyApiKey=secret" in resolved["tavily"]["url"]


def test_get_mcp_servers_config_resolves_tinyfish_header(monkeypatch):
    monkeypatch.setenv("TINYFISH_API_KEY", "tiny-secret")

    resolved = get_mcp_servers_config()
    assert resolved["tinyfish"]["headers"]["X-API-Key"] == "tiny-secret"


def test_get_mcp_servers_config_applies_override():
    resolved = get_mcp_servers_config(override={"new-server": {"transport": "sse", "url": "https://example.com"}})
    assert resolved["new-server"]["url"] == "https://example.com"
