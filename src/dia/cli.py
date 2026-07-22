"""CLI entry point for dia."""

from typing import Annotated

import typer

from dia import __version__

app = typer.Typer(
    name="dia",
    help="Department Intelligence Agent - knowledge graph extraction pipeline.",
    no_args_is_help=True,
)

ledger_app = typer.Typer(help="Inspect and manage the processing ledger.")
app.add_typer(ledger_app, name="ledger")


@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(False, "--version", "-v", help="Print version and exit."),
):
    """Department Intelligence Agent - knowledge graph extraction pipeline."""
    if version:
        typer.echo(f"dia {__version__}")
        raise typer.Exit()


@app.command("extract-text")
def extract_text(
    source: Annotated[str, typer.Option("--source", "-s", help="Source name from KNOWN_SOURCES.")],
    output: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Local directory to write extracted text to."),
    ] = None,
    live: Annotated[
        bool,
        typer.Option("--live", help="Write to the production S3 bucket + DynamoDB ledger."),
    ] = False,
    log_dir: Annotated[
        str | None,
        typer.Option("--log-dir", help="Directory for log files. Defaults to ./logs/."),
    ] = None,
):
    """Run Stage 1: extract text from documents.

    Three modes:

    \b
    - No --output, no --live: dry run. Reports how many documents would be
      processed (checked against the DynamoDB ledger) without downloading
      or writing anything.
    - --output <path>: local extraction. Downloads, extracts, and writes
      JSON to disk. Ledger is always a local file at <path>/.ledger.json —
      never touches the production ledger. Use `dia ledger clone` first if
      you want to test against real processed state.
    - --live: production extraction. Writes to the text-extracted S3
      bucket and the DynamoDB ledger, both resolved from your AWS account.
    """
    from dia.sources.known import get_source
    from dia.sources.s3 import S3DocumentSource

    if output and live:
        typer.echo("Error: Provide --output or --live, not both.")
        raise typer.Exit(code=1)

    try:
        data_source = get_source(source)
    except KeyError:
        typer.echo(f"Error: Unknown source {source!r}. Use --help to see available sources.")
        raise typer.Exit(code=1) from None

    document_source = S3DocumentSource(data_source=data_source)

    if not output and not live:
        _dry_run(source, document_source)
        return

    if live:
        _run_live(source, document_source, log_dir)
    else:
        _run_local(document_source, output, log_dir)


def _dry_run(source_name: str, document_source) -> None:
    """Report what --live would process, without downloading or writing anything."""
    from dia.cli_helpers import resolve_ledger_table
    from dia.ledger.dynamodb import DynamoDBLedger

    refs = document_source.list_documents()
    total = len(refs)

    table_name = resolve_ledger_table()
    ledger = DynamoDBLedger(table_name=table_name)
    pending = ledger.get_unprocessed(refs, source_name, "text")

    typer.echo(f"Source: {source_name} ({document_source.data_source.document_type})")
    typer.echo(f"Bucket: {document_source.data_source.bucket}")
    typer.echo(f"Total documents:    {total}")
    typer.echo(f"Already processed:  {total - len(pending)}")
    typer.echo(f"Would process:      {len(pending)}")
    typer.echo("")
    typer.echo("Use --output <path> for local extraction, or --live for production.")


def _run_live(source_name: str, document_source, log_dir: str | None) -> None:
    """Production mode: S3 output + DynamoDB ledger, both resolved from AWS account."""
    from dia.cli_helpers import resolve_ledger_table, resolve_text_output_bucket
    from dia.config import TextExtractionConfig
    from dia.ledger.dynamodb import DynamoDBLedger
    from dia.pipeline import TextExtractionRunner

    table_name = resolve_ledger_table()
    output_bucket = resolve_text_output_bucket()
    ledger = DynamoDBLedger(table_name=table_name)

    typer.echo(f"Live mode: output={output_bucket} ledger={table_name}")

    runner = TextExtractionRunner(
        source=document_source,
        ledger=ledger,
        config=TextExtractionConfig(),
        output_bucket=output_bucket,
        log_dir=log_dir,
    )
    _run_and_report(runner)


def _run_local(document_source, output: str, log_dir: str | None) -> None:
    """Local mode: writes to disk, always uses a local file ledger.

    Never touches the production ledger — safe to run repeatedly without
    affecting --live state. Use `dia ledger clone` to seed the local
    ledger with real processed state if needed.
    """
    from pathlib import Path

    from dia.config import TextExtractionConfig
    from dia.ledger.file import JsonFileLedger
    from dia.pipeline import TextExtractionRunner

    output_dir = Path(output)
    ledger_path = output_dir / ".ledger.json"
    ledger = JsonFileLedger(ledger_path)

    typer.echo(f"Local mode: output={output_dir} ledger={ledger_path}")

    runner = TextExtractionRunner(
        source=document_source,
        ledger=ledger,
        config=TextExtractionConfig(),
        output_dir=output_dir,
        log_dir=log_dir,
    )
    _run_and_report(runner)


def _run_and_report(runner) -> None:
    """Run the pipeline and print the result summary."""
    result = runner.run()

    typer.echo("")
    typer.echo("--- Text Extraction Result ---")
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


@ledger_app.command("list")
def ledger_list(
    source: Annotated[str, typer.Option("--source", "-s", help="Source name to list records for.")],
):
    """List processed documents for a source."""
    from dia.cli_helpers import resolve_ledger_table
    from dia.ledger.dynamodb import DynamoDBLedger

    table_name = resolve_ledger_table()
    ledger = DynamoDBLedger(table_name=table_name)
    records = ledger.list_records(source)

    if not records:
        typer.echo(f"No records found for source {source!r} in table {table_name}")
        raise typer.Exit()

    typer.echo(f"Source: {source}")
    typer.echo(f"Table:  {table_name}")
    typer.echo(f"Count:  {len(records)}")
    typer.echo("")

    for record in records:
        key = record.get("document_key", "")
        processed_at = record.get("processed_at", "?")
        code_version = record.get("code_version", "?")
        # Extract the document key portion (after source_name#)
        parts = key.split("#", 1)
        doc_key = parts[1] if len(parts) > 1 else key
        typer.echo(f"  {doc_key:<50} ({processed_at})  {code_version}")


@ledger_app.command("clear")
def ledger_clear(
    source: Annotated[str | None, typer.Option("--source", "-s", help="Source name to clear.")] = None,
    all_sources: Annotated[bool, typer.Option("--all", help="Clear ALL records across all sources.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview what would be deleted.")] = False,
):
    """Clear processed records from the ledger.

    Use --source to clear a single source, or --all to clear everything.
    Use --dry-run to preview without deleting.
    """
    from dia.cli_helpers import resolve_ledger_table
    from dia.ledger.dynamodb import DynamoDBLedger

    if not source and not all_sources:
        typer.echo("Error: Provide --source <name> or --all")
        raise typer.Exit(code=1)

    table_name = resolve_ledger_table()
    ledger = DynamoDBLedger(table_name=table_name)

    if all_sources:
        if dry_run:
            # Count all records via a scan
            records = []
            for src in _discover_sources(ledger):
                records.extend(ledger.list_records(src))
            typer.echo(f"Would delete {len(records)} records from table {table_name}")
            typer.echo("Run without --dry-run to apply.")
            raise typer.Exit()

        deleted = ledger.clear_all()
        typer.echo(f"Deleted {deleted} records from table {table_name}")
    else:
        records = ledger.list_records(source)
        if dry_run:
            typer.echo(f"Would delete {len(records)} records for source {source!r}")
            typer.echo("Run without --dry-run to apply.")
            raise typer.Exit()

        deleted = ledger.clear(source)
        typer.echo(f"Deleted {deleted} records for source {source!r} from table {table_name}")


def _discover_sources(ledger) -> set[str]:
    """Scan the ledger to find all unique source names."""
    sources: set[str] = set()
    scan_kwargs: dict = {"ProjectionExpression": "document_key"}

    while True:
        response = ledger._table.scan(**scan_kwargs)
        for item in response.get("Items", []):
            key = item.get("document_key", "")
            source_name = key.split("#", 1)[0]
            if source_name:
                sources.add(source_name)
        if "LastEvaluatedKey" not in response:
            break
        scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

    return sources
