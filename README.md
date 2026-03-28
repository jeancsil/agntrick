<div align="center">

# 🎩 Agntrick
**Build AI agents that *actually* do things.**

[![PyPI version](https://img.shields.io/pypi/v/agntrick?style=plastic&logo=pypi&logoColor=white)](https://pypi.org/project/agntrick/)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue?style=plastic&logo=python&logoColor=white)](https://python.org)
[![LangChain](https://img.shields.io/badge/langchain-%23007BA7.svg?style=plastic&logo=langchain&logoColor=white)](https://python.langchain.com/)
[![MCP](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-green?style=plastic&logo=modelcontextprotocol&logoColor=white)](https://modelcontextprotocol.io/)
[![License](https://img.shields.io/github/license/jeancsil/agntrick?style=plastic)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/jeancsil/agntrick/ci.yml?style=plastic&logo=github&label=Build)](https://github.com/jeancsil/agntrick/actions)
[![Coverage](https://img.shields.io/badge/coverage-80%25-brightgreen?style=plastic)](https://github.com/jeancsil/agntrick)

<br>

Combine **local tools** and **MCP servers** in a single, elegant runtime.
Write agents in **5 lines of code**. Run them anywhere.

</div>

---

## 💡 Why Agntrick?

Instead of spending days wiring together LLMs, tools, and execution environments, Agntrick gives you a production-ready setup instantly.

*   **Write Less, Do More:** Create a fully functional agent with just 5 lines of Python using the zero-config `@AgentRegistry.register` decorator.
*   **Context is King (MCP):** Native integration with Model Context Protocol (MCP) servers to give your agents live data (Web search, APIs, internal databases).
*   **Hardcore Local Tools:** Built-in blazing fast tools (`ripgrep`, `fd`, AST parsing) so your agents can explore and understand local codebases out-of-the-box.
*   **Stateful & Resilient:** Powered by **LangGraph** to support memory, cyclic reasoning, and human-in-the-loop workflows.
*   **Docker-First Isolation:** Every agent runs in isolated containers—no more "it works on my machine" when sharing with your team.

---

## 📦 Installation

### From PyPI

```bash
pip install agntrick

# Or with development dependencies
pip install "agntrick[dev]"
```

### From Source

```bash
git clone https://github.com/jeancsil/agntrick.git
cd agntrick
make install
```

---

## 🚀 Quick Start

### 1. Add your Brain (API Key)

You need an **LLM API key** to breathe life into your agents. Agntrick supports 10+ LLM providers via LangChain!

```bash
# Copy the template
cp .env.example .env

# Edit .env and paste your API key
# Choose one of the following providers:
# OPENAI_API_KEY=sk-your-key-here
# ANTHROPIC_API_KEY=sk-ant-your-key-here
# GOOGLE_API_KEY=your-google-key
# GROQ_API_KEY=gsk-your-key-here
# MISTRAL_API_KEY=your-mistral-key-here
# COHERE_API_KEY=your-cohere-key-here

# For Ollama (local), no API key needed:
# OLLAMA_BASE_URL=http://localhost:11434
```

### 2. Run Your First Agent

```bash
# List all available agents
agntrick list

# Run an agent with input
agntrick developer -i "Explain this codebase"

# Or try the learning agent with web search
agntrick learning -i "Explain quantum computing in simple terms"
```

<details>
<summary><strong>🔑 Supported Environment Variables</strong></summary>

Only one provider's API key is required. The framework auto-detects which provider to use based on available credentials.

```bash
# Anthropic (Recommended)
ANTHROPIC_API_KEY=sk-ant-your-key-here

# OpenAI
OPENAI_API_KEY=sk-your-key-here

# Google GenAI / Vertex
GOOGLE_API_KEY=your-google-key
GOOGLE_VERTEX_PROJECT_ID=your-project-id

# Mistral AI
MISTRAL_API_KEY=your-mistral-key-here

# Cohere
COHERE_API_KEY=your-cohere-key-here

# Azure OpenAI
AZURE_OPENAI_API_KEY=your-azure-key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com

# AWS Bedrock
AWS_PROFILE=your-profile

# Ollama (Local, no API key needed)
OLLAMA_BASE_URL=http://localhost:11434

# Hugging Face
HUGGINGFACEHUB_API_TOKEN=your-hf-token
```

📖 **See [docs/llm-providers.md](docs/llm-providers.md)** for detailed environment variable configurations and provider comparison.

</details>

---

## 🧰 Available Out of the Box

### 🤖 Bundled Agents

Agntrick includes several pre-built agents for common use cases:

| Agent | Purpose | MCP Servers |
|-------|---------|-------------|
| `committer` | Git Helper: Analyze changes and generate conventional commit messages | - |
| `developer` | Code Master: Read, search & edit code | `fetch` |
| `github-pr-reviewer` | PR Reviewer: Reviews diffs, posts inline comments & summaries | - |
| `learning` | Tutor: Step-by-step tutorials and explanations | `fetch`, `web-forager` |
| `news` | News Anchor: Aggregates top stories | `fetch` |
| `ollama` | Local Agent: Uses local GLM-4.7-Flash via Ollama (port 8080) | `fetch` |
| `youtube` | Video Analyst: Extract insights from YouTube videos | `fetch` |
| `whatsapp-multi-tenant` | WhatsApp Assistant: Multi-tenant messaging via WhatsApp API | - |

📖 **See [docs/agents.md](docs/agents.md)** for detailed information about each agent.

---

### 📦 Local Tools

Fast, zero-dependency tools for working with local codebases:

| Tool | Capability |
|------|------------|
| `find_files` | Fast search via `fd` |
| `discover_structure` | Directory tree mapping |
| `get_file_outline` | AST signature parsing |
| `read_file_fragment` | Precise file reading |
| `code_search` | Fast search via `ripgrep` |
| `edit_file` | Safe file editing |
| `youtube_transcript` | Extract transcripts from YouTube videos |

📖 **See [docs/tools.md](docs/tools.md)** for detailed documentation of each tool.

---

### 🌐 MCP Servers

Model Context Protocol servers for extending agent capabilities:

| Server | Purpose |
|--------|---------|
| `fetch` | Extract clean text from URLs |
| `web-forager` | Web search and content fetching |
| `kiwi-com-flight-search` | Search real-time flights |

📖 **See [docs/mcp-servers.md](docs/mcp-servers.md)** for details on each server and how to add custom MCP servers.

---

### 🧠 LLM Providers

Agntrick supports **10 LLM providers** out of the box, covering 90%+ of the market:

| Provider | Type | Use Case |
|----------|------|----------|
| **Anthropic** | Cloud | State-of-the-art reasoning (Claude) |
| **OpenAI** | Cloud | GPT-4, GPT-4.1, o1 series |
| **Azure OpenAI** | Cloud | Enterprise OpenAI deployments |
| **Google GenAI** | Cloud | Gemini models via API |
| **Google Vertex AI** | Cloud | Gemini models via GCP |
| **Mistral AI** | Cloud | European privacy-focused models |
| **Cohere** | Cloud | Enterprise RAG and Command models |
| **AWS Bedrock** | Cloud | Anthropic, Titan, Meta via AWS |
| **Ollama** | Local | Run LLMs locally (zero API cost) |
| **Hugging Face** | Cloud | Open models from Hugging Face Hub |

📖 **See [docs/llm-providers.md](docs/llm-providers.md)** for detailed setup instructions.

---

## 🛠️ Build Your Own Agent

### The 5-Line Superhero 🦸‍♂️

```python
from agntrick import AgentBase, AgentRegistry

@AgentRegistry.register("my-agent", mcp_servers=["fetch"])
class MyAgent(AgentBase):
    @property
    def system_prompt(self) -> str:
        return "You are my custom agent with the power to fetch websites."
```

Boom. Run it instantly:
```bash
agntrick my-agent -i "Summarize https://example.com"
```

### Advanced: Custom Local Tools 🔧

Want to add your own Python logic? Easy.

```python
from langchain_core.tools import StructuredTool
from agntrick import AgentBase, AgentRegistry

@AgentRegistry.register("data-processor")
class DataProcessorAgent(AgentBase):
    @property
    def system_prompt(self) -> str:
        return "You process data files like a boss."

    def local_tools(self) -> list:
        return [
            StructuredTool.from_function(
                func=self.process_csv,
                name="process_csv",
                description="Process a CSV file path",
            )
        ]

    def process_csv(self, filepath: str) -> str:
        # Magic happens here ✨
        return f"Successfully processed {filepath}!"
```

---

## ⚙️ Configuration

Agntrick can be configured via a `.agntrick.yaml` file in your project root or home directory:

```yaml
# .agntrick.yaml
llm:
  provider: anthropic  # or openai, google, ollama, etc.
  model: claude-sonnet-4-6  # optional model override
  temperature: 0.7

mcp:
  servers:
    - fetch
    - web-forager

logging:
  level: INFO
  file: logs/agent.log

whatsapp:
  tenants:
    - id: personal
      phone: "+34611111111"
      default_agent: developer
      allowed_contacts: []
  api:
    host: 127.0.0.1
    port: 8000
  storage:
    base_path: ~/.local/share/agntrick
  auth:
    api_keys:
      "admin-key-123": "admin"
```

## 🚀 Docker Quick Start

### Build and Run with Docker

```bash
# Build the Docker image (multi-stage build)
make docker-build

# Run the WhatsApp API server
docker compose up -d

# View logs
tail -f logs/agntrick.log
```

### Docker Benefits

- **Memory Efficient**: Limited to 512MB memory usage
- **Health Checks**: Built-in `/health` endpoint monitoring
- **Isolated Environment**: Consistent development and production environment
- **Multi-Stage Build**: Optimized image with Go gateway + Python API

### Quick Development

```bash
# Run tests in Docker environment
docker compose run --rm app make test

# Interactive development with mounted volumes
docker compose run --rm app agntrick developer -i "Examine this codebase"
```

### Quick Configuration

For WhatsApp setup, use environment variables:

```bash
export AGNTRICK_CONFIG=$(cat <<'EOF'
llm:
  provider: openai
  model: gpt-4o-mini
  temperature: 0.8

api:
  host: 127.0.0.1
  port: 8000

storage:
  base_path: ~/.local/share/agntrick

logging:
  level: INFO
  file: logs/agntrick.log

auth:
  api_keys:
    "admin-key-123": "admin"

whatsapp:
  tenants:
    - id: personal
      phone: "+34611111111"
      default_agent: developer
      allowed_contacts: []
EOF
)

echo $AGNTRICK_CONFIG > .agntrick.yaml
```

---

## 💻 CLI Reference

Command your agents directly from the terminal.

```bash
# 📋 List all registered agents
agntrick list

# 🕵️ Get detailed info about what an agent can do
agntrick info developer

# 🚀 Run an agent with input
agntrick developer -i "Analyze the architecture of this project"

# 🌐 Start the FastAPI server (multi-tenant WhatsApp support)
agntrick serve

# ⏱️ Run with an execution timeout (seconds)
agntrick developer -i "Refactor this module" -t 120

# 📝 Run with debug-level verbosity
agntrick developer -i "Hello" -v

# 📜 View logs
tail -f logs/agent.log

# 🔍 Check WhatsApp QR codes for a tenant
curl http://localhost:8000/api/v1/whatsapp/qr/personal/page
```

### Multi-Tenant CLI Commands

```bash
# Start server with custom config
agntrick serve --config .agntrick.yaml

# Start server with specific host/port
agntrick serve --host 0.0.0.0 --port 8080

# Server with debug logging
agntrick serve --log-level DEBUG

# Check API health
curl http://localhost:8000/health

# List available agents via API
curl http://localhost:8000/api/v1/agents

# Execute agent via API
curl -X POST http://localhost:8000/api/v1/agents/developer/run \
  -H "Authorization: Bearer admin-key-123" \
  -d '{"input": "Explain this codebase"}'
```

---

## 🏗️ Architecture

Under the hood, we seamlessly bridge the gap between user intent and execution:

### Multi-Tenant WhatsApp Architecture

```mermaid
flowchart TB
    subgraph User [👤 User Space]
        Input[User Input]
    end

    subgraph CLI [💻 CLI - agntrick]
        Typer[Typer Interface]
    end

    subgraph Registry [📋 Registry]
        AR[AgentRegistry]
        AD[Auto-discovery]
    end

    subgraph Agents [🤖 Agents]
        Dev[developer agent]
        Learning[learning agent]
        News[news agent]
        WA[WhatsApp multi-tenant]
    end

    subgraph Core [🧠 Core Engine]
        AB[AgentBase]
        LG[LangGraph Runtime]
        CP[(Checkpointing)]
    end

    subgraph Tools [🧰 Tools & Skills]
        LT[Local Tools]
        MCP[MCP Tools]
    end

    subgraph API [🌐 FastAPI Server]
        API1[GET /health]
        API2[POST /api/v1/agents/{name}/run]
        API3[POST /api/v1/channels/whatsapp/message]
        API4[GET /api/v1/whatsapp/qr/{tenant_id}]
    end

    subgraph Gateway [🚪 Go Gateway]
        GW1[WhatsApp Session Manager]
        GW2[Message Handler]
        GW3[QR Code Generator]
    end

    subgraph External [🌍 External World]
        LLM[LLM API]
        MCPS[MCP Servers]
        WA-API[WhatsApp API]
    end

    Input --> Typer
    Typer --> AR
    AR --> AD
    AR -->|Routes to| Dev & Learning & News & WA

    Dev & Learning & News & WA -->|Inherits from| AB

    AB --> LG
    LG <--> CP
    AB -->|Uses| LT
    AB -->|Uses| MCP

    LT -->|Reasoning| LLM
    MCP -->|Queries| MCPS
    MCPS -->|Provides Data| LLM

    AB --> API
    API --> Gateway
    Gateway --> WA-API
    WA-API -->|Multi-tenant| GW1 & GW2 & GW3

    LLM --> Output[Final Response]
```

### API Endpoints

The WhatsApp Multi-Tenant API provides the following endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check endpoint |
| `GET` | `/ready` | Readiness check endpoint |
| `GET` | `/api/v1/agents` | List all available agents |
| `POST` | `/api/v1/agents/{name}/run` | Execute an agent with input |
| `GET` | `/api/v1/whatsapp/qr/{tenant_id}` | SSE stream for QR codes |
| `GET` | `/api/v1/whatsapp/qr/{tenant_id}/page` | HTML QR code page |
| `POST` | `/api/v1/whatsapp/qr/{tenant_id}` | Receive QR from Go gateway |
| `POST` | `/api/v1/whatsapp/status/{tenant_id}` | Connection status update |
| `POST` | `/api/v1/channels/whatsapp/message` | WhatsApp webhook for incoming messages |

### Key Components

1. **Go Gateway** (`gateway/`): Multi-tenant WhatsApp session management via whatsmeow
   - `config.go` - YAML config parsing
   - `session.go` - WhatsApp session manager
   - `message.go` - Message handling with self-message detection
   - `http_client.go` - HTTP client for Python API communication
   - `qr.go` - QR code generation

2. **Python API** (`src/agntrick/api/`):
   - FastAPI server with tenant-scoped database isolation
   - API key authentication
   - Agent execution endpoints
   - WhatsApp webhook handling
   - QR code SSE streaming
   - Middleware (request logging, error handling)
   - Security (rate limiting, input sanitization)

3. **WhatsApp Module** (`src/agntrick/whatsapp/`):
   - Phone-to-tenant registry

## 🧪 Multi-Tenant WhatsApp Features

---

## 🧑‍💻 Local Development

<details>
<summary><strong>System Requirements & Setup</strong></summary>

**Requirements:**
- Python 3.12+
- `uv` package manager
- `ripgrep`, `fd`, `fzf` (for local tools)

```bash
# Install dependencies (blazingly fast with uv ⚡)
make install

# Run the test suite
make test

# Run agents directly
agntrick developer -i "Hello"
```
</details>

<details>
<summary><strong>Useful `make` Commands</strong></summary>

```bash
make install    # Install dependencies with uv
make test       # Run pytest with coverage
make format     # Auto-format codebase with ruff
make check      # Strict linting (mypy + ruff)
make build      # Build wheel and sdist packages
make build-clean # Remove build artifacts
```
</details>

<details>
<summary><strong>📦 Release Commands</strong></summary>

Automated release commands for publishing to PyPI:

```bash
# Release core agntrick package
make release VERSION=0.3.0

# Release agntrick-whatsapp package
make release-whatsapp VERSION=0.4.0

# Release both packages with different versions
make release-both CORE=0.3.0 WHATSAPP=0.4.0
```

📖 **See [RELEASING.md](RELEASING.md)** for complete release documentation, troubleshooting, and manual release procedures.
</details>

---

## 🤝 Contributing

We love contributions! Check out our [AGENTS.md](AGENTS.md) for development guidelines.

**For maintainers:** See [RELEASING.md](RELEASING.md) for how to publish new versions to PyPI.

**The Golden Rules:**
1. `make check` should pass without complaints.
2. `make test` should stay green.
3. Don't drop test coverage (we like our 80% mark!).

---

## 📄 License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) for details.

---

<p align="center">
  <strong>Stand on the shoulders of giants:</strong><br>
  <a href="https://python.langchain.com/"><img src="https://img.shields.io/badge/LangChain-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white" height="28" alt="LangChain"></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-Protocol-4B32C3?style=for-the-badge" height="28" alt="MCP"></a>
  <a href="https://github.com/langchain-ai/langgraph"><img src="https://img.shields.io/badge/LangGraph-FF0000?style=for-the-badge" height="28" alt="LangGraph"></a>
</p>

<p align="center">
  If you find this useful, please consider giving it a ⭐ or buying me a coffee!<br>
  <a href="https://github.com/jeancsil/agntrick/stargazers">
    <img src="https://img.shields.io/github/stars/jeancsil/agntrick?style=social&size=large" height="28" alt="Star the repo" style="vertical-align: middle;">
  </a>
  &nbsp;
  <a href="https://buymeacoffee.com/jeancsil" target="_blank">
    <img src="https://img.shields.io/badge/Buy_Me_A_Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black" height="28" alt="Buy Me A Coffee" style="vertical-align: middle;">
  </a>
</p>
