"""CLI entry point for dia."""

from typing import Annotated

import typer

from dia import __version__

app = typer.Typer(
    name="dia",
    help="Department Intelligence Agent - knowledge graph extraction pipeline.",
    no_args_is_help=True,
)


@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(False, "--version", "-v", help="Print version and exit."),
):
    """Department Intelligence Agent - knowledge graph extraction pipeline."""
    if version:
        typer.echo(f"dia {__version__}")
        raise typer.Exit()


@app.command()
def extract(
    source: Annotated[str, typer.Option("--source", "-s", help="Source name from KNOWN_SOURCES.")],
    log_dir: Annotated[
        str | None,
        typer.Option("--log-dir", help="Directory for log files. Defaults to ./logs/."),
    ] = None,
):
    """Run the extraction pipeline for a document source.

    Discovers documents, filters already-processed ones via the ledger,
    extracts text, and records progress. GraphRAG integration is stubbed
    for now — this validates the full pipeline flow.
    """
    from dia.ledger.memory import InMemoryLedger
    from dia.pipeline import PipelineRunner
    from dia.sources.known import get_source
    from dia.sources.s3 import S3DocumentSource

    # Resolve source
    try:
        data_source = get_source(source)
    except KeyError:
        typer.echo(f"Error: Unknown source {source!r}. Use --help to see available sources.")
        raise typer.Exit(code=1) from None

    # Build the document source
    document_source = S3DocumentSource(data_source=data_source)

    # For now, use in-memory ledger (DynamoDB wired in later PR)
    ledger = InMemoryLedger()

    # Run pipeline
    runner = PipelineRunner(
        source=document_source,
        ledger=ledger,
        source_name=source,
        log_dir=log_dir,
    )
    result = runner.run()

    # Summary output
    typer.echo("")
    typer.echo("--- Pipeline Result ---")
    typer.echo(f"  Total documents:  {result.total}")
    typer.echo(f"  Processed:        {result.processed}")
    typer.echo(f"  Skipped:          {result.skipped}")
    typer.echo(f"  Filtered out:     {result.filtered_out}")
    typer.echo(f"  Failed:           {result.failed}")
    typer.echo(f"  Duration:         {result.duration_seconds:.1f}s")

    if result.failed_keys:
        typer.echo("")
        typer.echo("Failed documents:")
        for key in result.failed_keys:
            typer.echo(f"  - {key}")

    if result.failed > 0:
        raise typer.Exit(code=1)
