import asyncio
import logging
import traceback
from pathlib import Path
from typing import Any, Callable, Type

import typer
import yaml
from rich.console import Console

from agentic_framework.channels import WhatsAppChannel
from agentic_framework.channels.whatsapp_config import WhatsAppAgentConfig
from agentic_framework.constants import LOGS_DIR
from agentic_framework.core.whatsapp_agent import WhatsAppAgent
from agentic_framework.mcp import MCPConnectionError, MCPProvider
from agentic_framework.registry import AgentRegistry

RUN_TIMEOUT_SECONDS = 600

app = typer.Typer(
    name="agentic-framework",
    help="A CLI for running agents in the Agentic Framework.",
    add_completion=True,
)
console = Console()
logger = logging.getLogger(__name__)


def configure_logging(verbose: bool) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level="DEBUG" if verbose else "INFO",
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="[%X]",
        handlers=[
            logging.FileHandler(str(LOGS_DIR / "agent.log")),
            logging.StreamHandler(),  # Also output to console
        ],
        force=True,
    )


def _print_chained_causes(error: BaseException) -> None:
    exc_ptr: BaseException | None = error
    while exc_ptr is not None:
        chained_cause: BaseException | None = getattr(exc_ptr, "__cause__", None) or getattr(
            exc_ptr, "__context__", None
        )
        if chained_cause is None:
            break
        console.print(f"[red]  cause: {chained_cause}[/red]")
        exc_ptr = chained_cause


def _handle_mcp_connection_error(error: MCPConnectionError) -> None:
    console.print(f"[bold red]MCP Connectivity Error:[/bold red] {error}")
    cause = error.cause

    if hasattr(cause, "exceptions"):
        for idx, sub_error in enumerate(cause.exceptions):
            console.print(f"[red]  sub-exception {idx + 1}: {sub_error}[/red]")
    elif error.__cause__:
        console.print(f"[red]  cause: {error.__cause__}[/red]")

    console.print("[yellow]Suggestion:[/yellow] Ensure the MCP server URL is correct and you have network access.")
    if "web-fetch" in error.server_name:
        console.print("[yellow]Note:[/yellow] web-fetch requires a valid remote URL. Check mcp/config.py")


async def _run_agent(
    agent_cls: Type[Any],
    input_text: str,
    allowed_mcp: list[str] | None,
) -> str:
    if allowed_mcp:
        provider = MCPProvider(server_names=allowed_mcp)
        async with provider.tool_session() as mcp_tools:
            agent = agent_cls(initial_mcp_tools=mcp_tools)
            return str(await agent.run(input_text))

    agent = agent_cls()
    return str(await agent.run(input_text))


def execute_agent(agent_name: str, input_text: str, timeout_sec: int) -> str:
    agent_cls = AgentRegistry.get(agent_name)
    if not agent_cls:
        raise typer.Exit(code=1)

    allowed_mcp = AgentRegistry.get_mcp_servers(agent_name)
    try:
        return asyncio.run(asyncio.wait_for(_run_agent(agent_cls, input_text, allowed_mcp), timeout=float(timeout_sec)))
    except asyncio.TimeoutError as exc:
        raise TimeoutError(f"Run timed out after {timeout_sec}s.") from exc


@app.command(name="list")
def list_agents() -> None:
    """List all available agents."""
    agents = AgentRegistry.list_agents()
    console.print(
        f"[bold magenta]Registry:[/bold magenta] [bold green]Available Agents:[/bold green] {', '.join(agents)}\n"
    )


@app.command(name="info")
def agent_info(agent_name: str = typer.Argument(..., help="Name of the agent to inspect.")) -> None:
    """Show detailed information about an agent."""
    agent_cls = AgentRegistry.get(agent_name)
    if not agent_cls:
        console.print(f"[bold red]Error:[/bold red] Agent '{agent_name}' not found.")
        console.print("[yellow]Tip:[/yellow] Use 'list' command to see all available agents.")
        raise typer.Exit(code=1)

    console.print(f"[bold cyan]Agent Details:[/bold cyan] {agent_name}\n")

    # Agent class name
    console.print(f"[bold]Class:[/bold] {agent_cls.__name__}")

    # Module
    console.print(f"[bold]Module:[/bold] {agent_cls.__module__}")

    # MCP servers
    mcp_servers = AgentRegistry.get_mcp_servers(agent_name)
    if mcp_servers is None:
        console.print("[bold]MCP Servers:[/bold] None (no MCP access)")
    elif mcp_servers:
        console.print(f"[bold]MCP Servers:[/bold] {', '.join(mcp_servers)}")
    else:
        console.print("[bold]MCP Servers:[/bold] (configured but empty list)")

    # Create agent instance first (needed for system prompt and tools)
    agent = None
    try:
        agent = agent_cls(initial_mcp_tools=[])  # type: ignore[call-arg]
    except Exception as e:
        console.print(f"[yellow]Warning:[/yellow] Could not instantiate agent: {e}")

    # System prompt (if available) - need to instantiate to access the property
    console.print("\n[bold]System Prompt:[/bold]")
    if agent and hasattr(agent, "system_prompt"):
        try:
            system_prompt = agent.system_prompt
            console.print(system_prompt)
        except Exception as e:
            console.print(f"[dim](Could not access system prompt: {e})[/dim]")
    else:
        console.print("[dim](No system prompt defined)[/dim]")

    # Tools info
    console.print("\n[bold]Tools:[/bold]")
    if agent:
        try:
            tools = agent.get_tools()

            if not tools:
                console.print("  No tools configured")
            else:
                for tool in tools:
                    tool_name = getattr(tool, "name", tool.__class__.__name__)
                    tool_desc = getattr(tool, "description", "(no description)")
                    console.print(f"  - [green]{tool_name}[/green]: {tool_desc}")
        except Exception as e:
            console.print(f"  [dim](Could not list tools: {e})[/dim]")
    else:
        console.print("  [dim](Could not instantiate agent to list tools)[/dim]")


def load_config(config_path: str) -> WhatsAppAgentConfig:
    """Load and validate configuration from a YAML file.

    Uses pydantic for type-safe configuration validation, ensuring
    all required fields are present and properly typed.

    Args:
        config_path: Path to the configuration file.

    Returns:
        Validated WhatsAppAgentConfig object.

    Raises:
        typer.Exit: If config file cannot be loaded or is invalid.
    """
    config_file = Path(config_path).expanduser()
    if not config_file.exists():
        console.print(f"[bold red]Error:[/bold red] Config file not found: {config_file}")
        console.print("[yellow]Tip: Copy config/whatsapp.yaml.example to config/whatsapp.yaml[/yellow]")
        raise typer.Exit(code=1)

    try:
        with config_file.open() as f:
            raw_config = yaml.safe_load(f) or {}
        # Validate using pydantic model
        return WhatsAppAgentConfig.model_validate(raw_config)
    except yaml.YAMLError as e:
        console.print(f"[bold red]Error:[/bold red] Failed to parse YAML: {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] Invalid configuration: {e}")
        # Provide helpful error message for common issues
        if "allowed_contact" in str(e):
            console.print("[yellow]Hint: Check that 'privacy.allowed_contact' is set in your config.[/yellow]")
        elif "storage_path" in str(e):
            console.print("[yellow]Hint: Check that 'channel.storage_path' is set in your config.[/yellow]")
        raise typer.Exit(code=1)


@app.command(name="whatsapp-bridge")
def whatsapp_command(
    config_path: str = typer.Option(
        "config/whatsapp.yaml",
        "--config",
        "-c",
        help="Path to WhatsApp configuration file.",
    ),
    allowed_contact: str | None = typer.Option(
        None,
        "--allowed-contact",
        help="Override allowed contact phone number.",
    ),
    storage: str | None = typer.Option(
        None,
        "--storage",
        help="Override storage directory for WhatsApp data.",
    ),
    mcp_servers: str | None = typer.Option(
        None,
        "--mcp-servers",
        help="Comma-separated MCP servers (e.g., 'web-fetch,duckduckgo-search'). Use 'none' to disable.",
    ),
    reset_session: bool = typer.Option(
        False,
        "--reset-session",
        help="Delete existing WhatsApp session to force QR code rescan.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging.",
    ),
) -> None:
    """Run the WhatsApp agent for bidirectional communication.

    This command starts a WhatsApp agent that listens for messages and
    responds using the configured LLM model. Use Ctrl+C to stop.

    First run will display a QR code for WhatsApp authentication.

    MCP Servers: By default, uses web-fetch and duckduckgo-search.
    Use --mcp-servers to customize or 'none' to disable.

    Session Management: WhatsApp sessions can expire or be invalidated by WhatsApp.
    Use --reset-session to delete the existing session and force a new QR code scan.
    """
    # Reconfigure logging if verbose
    if verbose:
        configure_logging(verbose=True)

    # Load and validate configuration
    config = load_config(config_path)

    # Apply CLI overrides
    storage_path = storage or str(config.get_storage_path())
    allowed_contact_value = allowed_contact or config.privacy.allowed_contact

    # Handle --reset-session: delete existing session file
    if reset_session:
        storage_dir = Path(storage_path).expanduser().resolve()

        # Find and delete session files (whatsmeow creates files named after the device)
        session_files = list(storage_dir.glob("*"))  # This catches the session file
        # Also look for whatsmeow-specific session files
        session_files.extend(list(storage_dir.glob("*.session*")))

        if session_files:
            console.print(f"[yellow]Deleting session files from:[/yellow] {storage_dir}")
            for session_file in session_files:
                # Keep the deduplication DB, delete everything else
                if session_file.name != "processed_messages.db":
                    console.print(f"  [dim]Removing:[/dim] {session_file.name}")
                    session_file.unlink()
            console.print("[green]Session cleared. QR code will be required on next run.[/green]")
            return  # Exit after resetting session
        else:
            console.print("[yellow]No session files found to delete.[/yellow]")

    # Parse MCP servers from CLI override (takes precedence)
    mcp_servers_list: list[str] | None = None
    if mcp_servers is not None:
        if mcp_servers.lower() in ("none", "", "disabled"):
            mcp_servers_list = []
        else:
            mcp_servers_list = [s.strip() for s in mcp_servers.split(",") if s.strip()]
    else:
        mcp_servers_list = config.mcp_servers

    # Display startup information
    console.print("[bold blue]Starting WhatsApp Agent...[/bold blue]")
    console.print(f"[dim]Storage:[/dim] {storage_path}")
    console.print(f"[dim]Allowed contact:[/dim] {allowed_contact_value}")
    console.print(f"[dim]Model:[/dim] {config.model or 'default'}")

    # Show MCP configuration
    if mcp_servers_list is not None:
        if mcp_servers_list:
            console.print(f"[dim]MCP Servers:[/dim] {', '.join(mcp_servers_list)} (custom)")
        else:
            console.print("[dim]MCP Servers:[/dim] disabled")
    else:
        default_mcp = AgentRegistry.get_mcp_servers("whatsapp-messenger") or []
        if default_mcp:
            console.print(f"[dim]MCP Servers:[/dim] {', '.join(default_mcp)} (default)")
        else:
            console.print("[dim]MCP Servers:[/dim] none configured")

    async def run_agent() -> None:
        """Run the WhatsApp agent with graceful shutdown."""
        # Create channel
        channel = WhatsAppChannel(
            storage_path=storage_path,
            allowed_contact=allowed_contact_value,
            log_filtered_messages=config.privacy.log_filtered_messages,
            typing_indicators=config.features.typing_indicators,
        )

        # Create agent with optional MCP servers override
        agent = WhatsAppAgent(
            channel=channel,
            model_name=config.model if config.model else None,
            mcp_servers_override=mcp_servers_list,
        )

        # Set up signal handlers for graceful shutdown
        shutdown_event = asyncio.Event()

        def signal_handler() -> None:
            console.print("\n[yellow]Shutdown requested...[/yellow]")
            shutdown_event.set()

        try:
            import signal

            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGINT, signal_handler)
            loop.add_signal_handler(signal.SIGTERM, signal_handler)
        except (AttributeError, NotImplementedError) as e:
            logger.debug(f"Signal handlers not available on this platform: {e}")

        # Start agent in a task
        agent_task = asyncio.create_task(agent.start())

        # Wait for shutdown signal
        await shutdown_event.wait()

        # Stop the agent
        console.print("[yellow]Stopping agent...[/yellow]")
        await agent.stop()
        agent_task.cancel()
        try:
            await agent_task
        except asyncio.CancelledError:
            pass

        console.print("[bold green]WhatsApp agent stopped.[/bold green]")

    # Run the agent
    try:
        asyncio.run(run_agent())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        console.print("[dim]Run with --verbose to see full traceback.[/dim]")
        raise typer.Exit(code=1)


# Alias for backwards compatibility - "whatsapp" redirects to "whatsapp-bridge"
@app.command(name="whatsapp", hidden=True)
def whatsapp_alias(
    config_path: str = typer.Option(
        "config/whatsapp.yaml",
        "--config",
        "-c",
        help="Path to WhatsApp configuration file.",
    ),
    allowed_contact: str | None = typer.Option(
        None,
        "--allowed-contact",
        help="Override allowed contact phone number.",
    ),
    storage: str | None = typer.Option(
        None,
        "--storage",
        help="Override storage directory for WhatsApp data.",
    ),
    mcp_servers: str | None = typer.Option(
        None,
        "--mcp-servers",
        help="Comma-separated MCP servers (e.g., 'web-fetch,duckduckgo-search'). Use 'none' to disable.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging.",
    ),
    reset_session: bool = typer.Option(
        False,
        "--reset-session",
        help="Delete existing WhatsApp session to force QR code rescan.",
    ),
) -> None:
    """Alias for whatsapp-bridge command."""
    whatsapp_command(
        config_path=config_path,
        allowed_contact=allowed_contact,
        storage=storage,
        mcp_servers=mcp_servers,
        verbose=verbose,
        reset_session=reset_session,
    )


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging."),
) -> None:
    """Agentic Framework CLI."""
    configure_logging(verbose)
    logging.info("Starting CLI")
    if ctx.invoked_subcommand is None:
        console.print("[bold yellow]No command provided. Use --help to see available commands.[/bold yellow]")


def create_agent_command(agent_name: str) -> Callable[[str, int], None]:
    def command(
        input_text: str = typer.Option(..., "--input", "-i", help="Input text for the agent."),
        timeout_sec: int = typer.Option(
            RUN_TIMEOUT_SECONDS,
            "--timeout",
            "-t",
            help="Max run time in seconds (MCP + LLM + tools).",
        ),
    ) -> None:
        """Run agent."""
        if not AgentRegistry.get(agent_name):
            console.print(f"[bold red]Error:[/bold red] Agent '{agent_name}' not found.")
            raise typer.Exit(code=1)

        console.print(f"[bold blue]Running agent:[/bold blue] {agent_name}...")

        try:
            result = execute_agent(agent_name=agent_name, input_text=input_text, timeout_sec=timeout_sec)
            console.print(f"[bold green]Result from {agent_name}:[/bold green]")
            console.print(result)
        except typer.Exit:
            raise
        except TimeoutError as error:
            console.print(
                "[bold red]Error running agent:[/bold red] "
                f"{error} Check MCP server connectivity or use --timeout to increase."
            )
            raise typer.Exit(code=1)
        except MCPConnectionError as error:
            _handle_mcp_connection_error(error)
            raise typer.Exit(code=1)
        except Exception as error:
            console.print(f"[bold red]Error running agent:[/bold red] {error}")
            _print_chained_causes(error)
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                console.print("[dim]" + traceback.format_exc() + "[/dim]")
            else:
                console.print("[dim]Run with --verbose to see full traceback.[/dim]")
            raise typer.Exit(code=1)

    command.__doc__ = f"Run the {agent_name} agent."
    return command


AgentRegistry.discover_agents()
for _name in AgentRegistry.list_agents():
    app.command(name=_name)(create_agent_command(_name))


if __name__ == "__main__":
    app()
