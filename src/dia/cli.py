"""CLI entry point for dia."""

import typer

from dia import __version__

app = typer.Typer(
    name="dia",
    help="Department Intelligence Agent - knowledge graph extraction pipeline.",
    no_args_is_help=True,
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", help="Print version and exit."),
):
    """Department Intelligence Agent - knowledge graph extraction pipeline."""
    if version:
        typer.echo(f"dia {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None and not version:
        # no_args_is_help handles this, but just in case
        pass
