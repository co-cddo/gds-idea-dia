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


@ledger_app.command("clone")
def ledger_clone(
    to: Annotated[
        str, typer.Option("--to", "-t", help="Path to write the local ledger JSON file.")
    ] = "output/ledger.json",
):
    """Clone the entire ledger from DynamoDB to a local JSON file.

    Copies every record from the production DynamoDB ledger into a local
    file compatible with JsonFileLedger. Use this to seed a local run so
    it skips already-processed documents.

    Overwrites the target file if it already exists.
    """
    import json
    from pathlib import Path

    from dia.cli_helpers import resolve_ledger_table
    from dia.ledger.dynamodb import DynamoDBLedger

    table_name = resolve_ledger_table()
    remote = DynamoDBLedger(table_name=table_name)

    records = remote.list_all_records()
    if not records:
        typer.echo(f"No records found in table {table_name}")
        raise typer.Exit()

    # Build the local ledger dict (same format JsonFileLedger uses on disk)
    data = {record["document_key"]: {k: v for k, v in record.items() if k != "document_key"} for record in records}

    target_path = Path(to)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    typer.echo(f"Cloned {len(records)} records from {table_name} → {target_path}")


def _discover_sources(ledger) -> set[str]:
    """Find all unique source names present in the ledger."""
    return {record["source_name"] for record in ledger.list_all_records() if record.get("source_name")}
