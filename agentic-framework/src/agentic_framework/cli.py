import asyncio
import logging
import traceback
from typing import Any, Type

import typer
from dotenv import load_dotenv
from rich.console import Console

from agentic_framework.constants import LOGS_DIR
from agentic_framework.mcp import MCPConnectionError, MCPProvider
from agentic_framework.registry import AgentRegistry

load_dotenv()

RUN_TIMEOUT_SECONDS = 600

app = typer.Typer(
    name="agentic-framework",
    help="A CLI for running agents in the Agentic Framework.",
    add_completion=True,
)
console = Console()


def configure_logging(verbose: bool) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level="DEBUG" if verbose else "INFO",
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="[%X]",
        handlers=[logging.FileHandler(str(LOGS_DIR / "agent.log"))],
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


def create_agent_command(agent_name: str):
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
