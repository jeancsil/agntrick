import logging


import typer
from rich.console import Console
from rich.panel import Panel

from agentic_framework.constants import LOGS_DIR
from agentic_framework.core.agent import SimpleAgent  # noqa: F401
from agentic_framework.core.chef_agent import ChefAgent  # noqa: F401
from agentic_framework.registry import AgentRegistry

app = typer.Typer(
    name="agentic-framework",
    help="A CLI for running agents in the Agentic Framework.",
    add_completion=False,
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
        console.print("[bold yellow]No command provided. " + "Use --help to see available commands.[/bold yellow]")


def create_agent_command(agent_name: str):
    def command(
        input_text: str = typer.Option(..., "--input", "-i", help="Input text for the agent."),
    ):
        """Run the {agent_name} agent."""

        agent_cls = AgentRegistry.get(agent_name)
        if not agent_cls:
            console.print(f"[bold red]Error:[/bold red] Agent '{agent_name}' not found.")
            raise typer.Exit(code=1)

        console.print(f"[bold blue]Running agent:[/bold blue] {agent_name}...")
        try:
            # Instantiate agent
            agent = agent_cls()

            result = agent.run(input_text)

            console.print(
                Panel(
                    str(result),
                    title=f"[bold green]Result from {agent_name}[/bold green]",
                )
            )

        except Exception as e:
            console.print(f"[bold red]Error running agent:[/bold red] {e}")
            # Verbose logging is configured in main callback,
            # but exception printing needs explicit handling if we want full trace
            # Since logging is configured, exceptions logged via logger.exception would
            # show up if verbose.
            # Here we just print the error message nicely.
            raise typer.Exit(code=1)

    command.__doc__ = f"Run the {agent_name} agent."
    # We need to set the name of the function to be unique
    # otherwise typer might get confused?
    # Actually Typer uses the function object.
    return command


# Dynamically register commands for each agent
for agent_name in AgentRegistry.list_agents():
    # Create a command function for this agent
    cmd_func = create_agent_command(agent_name)
    app.command(name=agent_name)(cmd_func)


if __name__ == "__main__":
    app()
