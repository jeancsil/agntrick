# Available Agents

User-facing catalog of built-in agents and how to run them.

## Agent Summary

| Agent | CLI command | Purpose | MCP access |
| --- | --- | --- | --- |
| `developer` | `bin/agent.sh developer -i "..."` | Explore, search, and edit codebases | `web-fetch` |
| `travel-coordinator` | `bin/agent.sh travel-coordinator -i "..."` | Orchestrate specialist travel planning | `kiwi-com-flight-search`, `web-fetch` |
| `chef` | `bin/agent.sh chef -i "..."` | Recipe suggestions from ingredients | `web-fetch` |
| `news` | `bin/agent.sh news -i "..."` | AI-news summarization | `web-fetch` |
| `travel` | `bin/agent.sh travel -i "..."` | Flight search and recommendations | `kiwi-com-flight-search` |
| `simple` | `bin/agent.sh simple -i "..."` | Minimal chat agent | None |
| `github-pr-reviewer` | `bin/agent.sh github-pr-reviewer -i "..."` | Pull request review automation | None |
| `whatsapp` | `bin/agent.sh whatsapp --config config/whatsapp.yaml` | WhatsApp message interface | `web-fetch`, `duckduckgo-search` |

## Developer Agent

Primary code-assistant agent with local tools for file discovery, search, outlines, fragment reads, and controlled edits.

Example:

```bash
bin/agent.sh developer -i "Find all uses of AgentRegistry.register"
```

## Travel Coordinator Agent

Composes specialist agents to produce a final travel recommendation from flight and destination inputs.

Example:

```bash
bin/agent.sh travel-coordinator -i "Plan a weekend trip from Madrid to Paris"
```

## Chef Agent

Suggests recipes from available ingredients.

Example:

```bash
bin/agent.sh chef -i "I have eggs, spinach, and feta. What can I cook?"
```

## News Agent

Summarizes current AI-focused news.

Example:

```bash
bin/agent.sh news -i "Give me today's most relevant AI headlines"
```

## Travel Agent

Finds flight options and returns a best-fit recommendation.

Example:

```bash
bin/agent.sh travel -i "Find flights from Madrid to Berlin next Friday"
```

## Simple Agent

General-purpose conversational baseline agent.

Example:

```bash
bin/agent.sh simple -i "Hello"
```

## GitHub PR Reviewer Agent

Reviews pull requests using GitHub API helper tools for diff retrieval and comment posting.

Example:

```bash
bin/agent.sh github-pr-reviewer -i "Review PR #123 in owner/repo"
```

## WhatsApp Agent

CLI command: `whatsapp`.
Registry name: `whatsapp-messenger`.

Setup:

```bash
cp agentic-framework/config/whatsapp.yaml.example agentic-framework/config/whatsapp.yaml
bin/agent.sh whatsapp --config config/whatsapp.yaml
```

Optional overrides:

```bash
bin/agent.sh whatsapp --allowed-contact "+1234567890" --storage ~/custom/path
bin/agent.sh whatsapp --mcp-servers "web-fetch,duckduckgo-search"
bin/agent.sh whatsapp --mcp-servers none
```

## Related Documentation

- Tool details: [tools.md](tools.md)
- MCP servers: [mcp-servers.md](mcp-servers.md)
- LLM providers: [llm-providers.md](llm-providers.md)
