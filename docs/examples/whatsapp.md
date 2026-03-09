# WhatsApp Integration

Agntrick includes WhatsApp support through the `agntrick-whatsapp` package.

## Installation

```bash
pip install agntrick[whatsapp]
# Or
pip install agntrick-whatsapp
```

## Features

- **Bidirectional**: Send and receive messages
- **QR Authentication**: Simple setup with QR code
- **Privacy-Focused**: Only configured contacts can interact
- **Slash Commands**: Route messages to different agent modes
- **Audio Support**: Transcribe and respond to voice messages

## Quick Start

### 1. Install Dependencies

```bash
pip install agntrick-whatsapp
```

Also requires:
- Go 1.21+ (for WhatsApp backend)
- ffmpeg (for audio processing)

### 2. Create Configuration

```bash
cp config/whatsapp.yaml.example config/whatsapp.yaml
```

Edit `config/whatsapp.yaml`:

```yaml
model: "claude-sonnet-4-6"

privacy:
  allowed_contact: "+1234567890"  # Your phone number

channel:
  storage_path: "~/storage/whatsapp"

mcp_servers:
  - fetch
  - web-forager
```

### 3. Run

```bash
agntrick whatsapp --config config/whatsapp.yaml
```

### 4. Authenticate

1. A QR code will appear in the terminal
2. Scan it with WhatsApp (Settings > Linked Devices)
3. Wait for connection confirmation

## Usage

### Basic Messaging

Just send a message to the agent:

```
You: What's the weather like?
Agent: I'll check that for you...
```

### Slash Commands

The WhatsApp agent supports command prefixes:

| Command | Description |
|---------|-------------|
| `/learn <topic>` | Learning mode with tutorials |
| `<any message>` | Default assistant mode |

```
You: /learn Python decorators
Agent: Let me teach you about Python decorators...

You: What's the latest news?
Agent: [Uses web search to find current news]
```

### Audio Messages

Voice messages are automatically transcribed:

```
You: [Voice message: "Explain quantum computing"]
Agent: Let me explain quantum computing...
```

## Configuration Options

| Option | Description |
|--------|-------------|
| `model` | LLM model to use |
| `mcp_servers` | MCP servers for capabilities |
| `privacy.allowed_contact` | Only this number can interact |
| `privacy.log_filtered_messages` | Log filtered messages |
| `channel.storage_path` | Session storage location |
| `features.group_messages` | Enable group chat (disabled by default) |

## Privacy & Security

- **Contact Filtering**: Only configured phone number can interact
- **Group Filtering**: Group messages are ignored by default
- **Local Storage**: All data stored locally, no cloud
- **Message Deduplication**: Prevents reprocessing

## Custom WhatsApp Agent

Create your own WhatsApp agent:

```python
from agntrick_whatsapp import WhatsAppAgent, WhatsAppConfig

config = WhatsAppConfig(
    model="claude-sonnet-4-6",
    allowed_contact="+1234567890",
    storage_path="~/whatsapp-data",
)

agent = WhatsAppAgent(config)
await agent.start()
```

## Troubleshooting

### QR Code Not Appearing

- Ensure terminal supports ANSI colors
- Try increasing terminal size
- Check for output redirection

### Connection Drops

- Check internet connection
- WhatsApp may rate-limit new connections
- Try again after a few minutes

### Audio Not Working

- Ensure ffmpeg is installed
- Check audio file format (supports most common formats)

## See Also

- [agntrick-whatsapp README](../../agentic-framework/packages/agntrick-whatsapp/README.md)
- [Custom Agents](../agents/custom.md) - Create custom agents
- [MCP Overview](../mcp/index.md) - MCP capabilities
