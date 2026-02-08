import asyncio
import logging
import traceback

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from agentic_framework.constants import LOGS_DIR
from agentic_framework.mcp import MCPProvider
from agentic_framework.registry import AgentRegistry

# Load environment variables once at the entry point
load_dotenv()

# Max time for the full agent run (MCP connection + LLM + tools). Prevents indefinite hang.
RUN_TIMEOUT_SECONDS = 90

app = typer.Typer(
    name="agentic-framework",
    help="A CLI for running agents in the Agentic Framework.",
    add_completion=True,
)
console = Console()


def configure_logging(verbose: bool):
    handlers = []
    handlers.append(logging.FileHandler(str(LOGS_DIR / "agent.log")))
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    logging.basicConfig(
        level="DEBUG" if verbose else "INFO",
        format=log_format,
        datefmt="[%X]",
        handlers=handlers,
        force=True,
    )


@app.command()
def list():
    """List all available agents."""
    agents = AgentRegistry.list_agents()
    console.print(
        Panel(
            f"[bold green]Available Agents:[/bold green] {', '.join(agents)}",
            title="Registry",
        )
    )


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging."),
):
    """
    Agentic Framework CLI. Use `list` to see available agents,
    or `<agent-name>` to run one.
    """
    configure_logging(verbose)
    logging.info("Starting CLI")
    if ctx.invoked_subcommand is None:
        console.print("[bold yellow]No command provided. Use --help to see available commands.[/bold yellow]")


def create_agent_command(agent_name: str):
    def command(
        input_text: str = typer.Option(..., "--input", "-i", help="Input text for the agent."),
        timeout_sec: int = typer.Option(
            RUN_TIMEOUT_SECONDS,
            "--timeout",
            "-t",
            help="Max run time in seconds (MCP + LLM + tools).",
        ),
    ):
        """Run the {agent_name} agent."""

        agent_cls = AgentRegistry.get(agent_name)
        if not agent_cls:
            console.print(f"[bold red]Error:[/bold red] Agent '{agent_name}' not found.")
            raise typer.Exit(code=1)

        console.print(f"[bold blue]Running agent:[/bold blue] {agent_name}...")
        try:
            allowed_mcp = AgentRegistry.get_mcp_servers(agent_name)

            async def _run():
                if allowed_mcp:
                    provider = MCPProvider(server_names=allowed_mcp)
                    async with provider.tool_session() as mcp_tools:
                        agent = agent_cls(initial_mcp_tools=mcp_tools)
                        return await agent.run(input_text)
                else:
                    agent = agent_cls()
                    return await agent.run(input_text)

            try:
                result = asyncio.run(asyncio.wait_for(_run(), timeout=float(timeout_sec)))
            except asyncio.TimeoutError:
                console.print(
                    f"[bold red]Error running agent:[/bold red] Run timed out after {timeout_sec}s. "
                    "Check MCP server connectivity or use --timeout to increase."
                )
                raise typer.Exit(code=1)

            console.print(
                Panel(
                    str(result),
                    title=f"[bold green]Result from {agent_name}[/bold green]",
                )
            )

        except typer.Exit:
            raise
        except Exception as e:
            console.print(f"[bold red]Error running agent:[/bold red] {e}")
            cause: BaseException | None = e
            while getattr(cause, "__cause__", None) is not None:
                cause = cause.__cause__  # type: ignore[union-attr]
                console.print(f"[red]  cause: {cause}[/red]")
            console.print("[dim]" + traceback.format_exc() + "[/dim]")
            raise typer.Exit(code=1)

    command.__doc__ = f"Run the {agent_name} agent."
    # We need to set the name of the function to be unique
    # otherwise typer might get confused?
    # Actually Typer uses the function object.
    return command


# Discover and register all agent CLI commands
AgentRegistry.discover_agents()
for agent_name in AgentRegistry.list_agents():
    # Create a command function for this agent
    cmd_func = create_agent_command(agent_name)
    app.command(name=agent_name)(cmd_func)


if __name__ == "__main__":
    app()
