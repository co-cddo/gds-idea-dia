"""CLI entry point for dia."""

from collections.abc import Iterator
from contextlib import contextmanager
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

pipeline_app = typer.Typer(help="Run and check the document pipeline.")
app.add_typer(pipeline_app, name="pipeline")

agent_app = typer.Typer(help="Query the digital intelligence agent.")
app.add_typer(agent_app, name="agent")


@agent_app.callback()
def _require_agent_extra() -> None:
    """Stop with a clear message if the agent's optional dependencies aren't installed."""
    try:
        import strands  # noqa: F401
    except ImportError:
        typer.echo("The agent commands need the 'agent' extra. Install it with: uv sync --extra agent")
        raise typer.Exit(code=1) from None


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
    from dia.cli_helpers import current_names
    from dia.ledger.dynamodb import DynamoDBLedger

    table_name = current_names()("ledger")
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
    from dia.cli_helpers import current_names
    from dia.ledger.dynamodb import DynamoDBLedger

    if not source and not all_sources:
        typer.echo("Error: Provide --source <name> or --all")
        raise typer.Exit(code=1)

    table_name = current_names()("ledger")
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

    from dia.cli_helpers import current_names
    from dia.ledger.dynamodb import DynamoDBLedger

    table_name = current_names()("ledger")
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


@pipeline_app.command("preflight")
def preflight(
    remote: Annotated[
        bool, typer.Option("--remote", help="Run the checks as a task in the cloud, where Neptune can be reached.")
    ] = False,
    no_wait: Annotated[
        bool, typer.Option("--no-wait", help="With --remote: start the task and return without following it.")
    ] = False,
) -> None:
    """Check that this process can do what the pipeline needs.

    Read-only. Reports your identity, the runtime config, the ledger table, our
    buckets and access to the source data. Inside an ECS task it also checks
    Neptune, which only tasks can reach. Exits with an error if any check fails.

    With --remote the checks run as a task, and this command follows its logs and
    exits with the task's exit code. It needs no confirmation, because it only reads.
    """
    if no_wait and not remote:
        raise typer.BadParameter("--no-wait only applies with --remote.", param_hint="--no-wait")

    if remote:
        _run_remote(["pipeline", "preflight"], wait=not no_wait)
        return

    from dia.preflight import Status, run_preflight

    labels = {Status.OK: "ok  ", Status.FAIL: "FAIL", Status.SKIP: "skip"}
    results = run_preflight()
    for result in results:
        typer.echo(f"[{labels[result.status]}] {result.name}: {result.detail}")

    failed = [r for r in results if r.status is Status.FAIL]
    if failed:
        typer.echo(f"\n{len(failed)} of {len(results)} checks failed.")
        raise typer.Exit(code=1)
    typer.echo(f"\nAll {len(results)} checks passed or were skipped.")


tasks_app = typer.Typer(help="Look at the pipeline's tasks in the cloud.")
pipeline_app.add_typer(tasks_app, name="tasks")


@contextmanager
def _exit_on_remote_error(hint: str = "") -> Iterator[None]:
    """Turn a failure to read the runtime config or reach ECS into a message and exit code 1.

    Args:
        hint: Extra text printed after the error, for example what to do next.
    """
    from dia.remote import RemoteError
    from dia.runtime_config import RuntimeConfigError

    try:
        yield
    except (RemoteError, RuntimeConfigError) as e:
        typer.echo(f"Error: {e}")
        if hint:
            typer.echo(hint)
        raise typer.Exit(code=1) from None


def _load_runtime_config():
    """The runtime config for the active credentials, or exit with a clear message."""
    from dia.cli_helpers import current_names
    from dia.runtime_config import RuntimeConfig

    with _exit_on_remote_error():
        return RuntimeConfig.load(current_names())


def _run_remote(command: list[str], wait: bool) -> None:
    """Start `dia <command>` as a task, and (unless told not to) follow it to the end.

    Exits with the task's exit code when following.
    """
    from dia import remote

    config = _load_runtime_config()
    with _exit_on_remote_error():
        started_by = remote.caller_started_by()
        task_id = remote.launch(config, command, started_by)

    typer.echo(f"Started task {task_id} ({' '.join(command)}) as {started_by}")
    follow_hint = f"dia pipeline tasks logs {task_id} --follow"
    if not wait:
        typer.echo(f"Follow it with: {follow_hint}")
        return

    try:
        with _exit_on_remote_error("The task may still be running. Check it with: dia pipeline tasks"):
            exit_code = remote.follow(config, task_id, typer.echo)
    except KeyboardInterrupt:
        typer.echo(f"\nStopped following. The task is still running. Follow it with: {follow_hint}")
        raise typer.Exit(code=130) from None

    if exit_code:
        raise typer.Exit(code=exit_code)


@tasks_app.callback(invoke_without_command=True)
def tasks(
    ctx: typer.Context,
    mine: Annotated[bool, typer.Option("--mine", help="Only tasks you started.")] = False,
) -> None:
    """List the pipeline's running and recently stopped tasks, newest first."""
    if ctx.invoked_subcommand is not None:
        return

    from dia import remote

    config = _load_runtime_config()
    with _exit_on_remote_error():
        started_by = remote.caller_started_by() if mine else None
        infos = remote.list_tasks(config, started_by=started_by)

    if not infos:
        typer.echo("No tasks found.")
    for info in infos:
        created = info.created_at.strftime("%Y-%m-%d %H:%M:%S") if info.created_at else "-"
        code = "-" if info.exit_code is None else str(info.exit_code)
        typer.echo(f"{info.task_id}  {info.status:<12} exit={code:<3} {created}  {info.started_by}  {info.command}")
    typer.echo(f"\nECS keeps stopped tasks for {remote.STOPPED_TASK_RETENTION}.")


@tasks_app.command("logs")
def tasks_logs(
    task_id: Annotated[str, typer.Argument(help="The task ID (see `dia pipeline tasks`).")],
    follow: Annotated[bool, typer.Option("--follow", "-f", help="Keep printing until the task stops.")] = False,
) -> None:
    """Print a task's logs. With --follow, exits with the task's exit code."""
    from dia import remote

    config = _load_runtime_config()
    try:
        with _exit_on_remote_error():
            if follow:
                exit_code = remote.follow(config, task_id, typer.echo)
                if exit_code:
                    raise typer.Exit(code=exit_code)
                return
            page = remote.read_log_page(config, task_id)
    except KeyboardInterrupt:
        raise typer.Exit(code=130) from None

    if not page.lines:
        typer.echo(f"No logs yet for task {task_id}.")
    for line in page.lines:
        typer.echo(line)


@tasks_app.command("stop")
def tasks_stop(task_id: Annotated[str, typer.Argument(help="The task ID (see `dia pipeline tasks`).")]) -> None:
    """Stop a running task."""
    from dia import remote

    config = _load_runtime_config()
    with _exit_on_remote_error():
        remote.stop(config, task_id)
    typer.echo(f"Asked ECS to stop task {task_id}.")


@app.command("extract-text")
def extract_text(
    source: Annotated[str, typer.Option("--source", "-s", help="Source name (e.g. gats-business-cases).")],
    departments: Annotated[
        str | None, typer.Option("--departments", "-d", help="Comma-separated department filter.")
    ] = None,
    execute: Annotated[bool, typer.Option("--execute", help="Run locally: writes to output/.")] = False,
    live: Annotated[bool, typer.Option("--live", help="Run in production: writes to S3 + DynamoDB.")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt for --live.")] = False,
    force: Annotated[bool, typer.Option("--force", "-f", help="Ignore the ledger and reprocess everything.")] = False,
    inmemory_ledger: Annotated[
        bool, typer.Option("--inmemory-ledger", help="Use an ephemeral ledger (only with --execute).")
    ] = False,
):
    """Extract text from documents in a source.

    Default (no --execute, no --live) is a preview: lists what would be
    processed without writing anything. Use --execute for a local run
    (writes to output/), or --live for a production run (writes to S3 +
    DynamoDB, with a confirmation prompt).
    """
    from dia.metadata import MetadataDepartmentFilter, load_metadata
    from dia.sources.known import KNOWN_SOURCES, get_source
    from dia.sources.s3 import S3DocumentSource

    if execute and live:
        typer.echo("Error: --execute and --live are mutually exclusive")
        raise typer.Exit(code=1)

    if inmemory_ledger and not execute:
        typer.echo("Error: --inmemory-ledger is only valid with --execute")
        raise typer.Exit(code=1)

    try:
        data_source = get_source(source)
    except KeyError:
        typer.echo(f"Error: Unknown source {source!r}. Known sources: {', '.join(sorted(KNOWN_SOURCES))}")
        raise typer.Exit(code=1) from None

    typer.echo(f"Source: {source}")

    s3_source = S3DocumentSource(data_source)
    typer.echo("Listing documents...", nl=False)
    all_refs = s3_source.list_documents()
    typer.echo(f" {len(all_refs)} found")

    typer.echo("Loading metadata...", nl=False)
    metadata = load_metadata(source, data_source.prefix, document_keys=[ref.key for ref in all_refs])
    typer.echo(" none configured" if metadata is None else f" {len(metadata)} entries loaded")

    filters = []
    if departments:
        if metadata is None:
            typer.echo(f"Error: Source {source!r} does not support department filtering")
            raise typer.Exit(code=1)
        department_list = [d.strip() for d in departments.split(",") if d.strip()]
        filters.append(MetadataDepartmentFilter(metadata, department_list))

    filtered_refs = all_refs
    for f in filters:
        filtered_refs = f.filter(filtered_refs)

    if not execute and not live:
        _preview(source, all_refs, filtered_refs, force)
        return

    if execute:
        _run_local(source, data_source, s3_source, metadata, filters, force, inmemory_ledger)
    else:
        _run_live(source, data_source, s3_source, metadata, filters, filtered_refs, force, yes)


def _preview(source: str, all_refs: list, filtered_refs: list, force: bool) -> None:
    """Report what --execute would do, without writing anything.

    Checks the local JsonFileLedger (output/ledger.json) rather than
    DynamoDB — this reports against the same ledger --execute would use,
    so it reflects local progress (e.g. an interrupted previous run).
    Use `dia ledger clone` to seed output/ledger.json from production,
    or `--live` to see production state directly.
    """
    from dia.ledger.file import JsonFileLedger

    if len(filtered_refs) != len(all_refs):
        typer.echo(f"After department filter: {len(filtered_refs)} (removed {len(all_refs) - len(filtered_refs)})")

    if force:
        typer.echo(f"To extract: {len(filtered_refs)} (--force: ignoring ledger)")
    else:
        ledger = JsonFileLedger("output/ledger.json")
        typer.echo("Checking ledger (output/ledger.json)...", nl=False)
        pending = ledger.get_unprocessed(filtered_refs, source, "text")
        already_done = len(filtered_refs) - len(pending)
        typer.echo(f" {already_done} already done, {len(pending)} to extract")

        if already_done == 0:
            typer.echo("Tip: run `dia ledger clone` to seed from production.")

    typer.echo("")
    typer.echo("Run with --execute for a local run, or --live for production.")


def _run_local(source, data_source, s3_source, metadata, filters, force, inmemory_ledger) -> None:
    """Run extraction locally: output/ writer, file-backed (or in-memory) ledger."""
    from dia.config import TextExtractionConfig
    from dia.ledger.file import JsonFileLedger
    from dia.ledger.memory import InMemoryLedger
    from dia.pipeline import TextExtractionRunner
    from dia.writers.local import LocalOutputWriter

    ledger = InMemoryLedger() if inmemory_ledger else JsonFileLedger("output/ledger.json")
    writer = LocalOutputWriter("output/")

    runner = TextExtractionRunner(
        source=s3_source,
        ledger=ledger,
        config=TextExtractionConfig(),
        writer=writer,
        metadata=metadata,
        filters=filters,
        force=force,
    )
    result = runner.run()
    _report_result(result)


def _run_live(source, data_source, s3_source, metadata, filters, filtered_refs, force, yes) -> None:
    """Run extraction in production: S3 writer, DynamoDB ledger, with confirmation."""
    from dia.cli_helpers import current_names
    from dia.config import TextExtractionConfig
    from dia.ledger.dynamodb import DynamoDBLedger
    from dia.naming import Bucket
    from dia.pipeline import TextExtractionRunner
    from dia.writers.s3 import S3OutputWriter

    names = current_names()
    table_name = names("ledger")
    bucket = names(Bucket.TEXT_EXTRACTED)
    ledger = DynamoDBLedger(table_name=table_name)
    writer = S3OutputWriter(bucket)

    if force:
        count = len(filtered_refs)
        verb = "REPROCESS"
        suffix = " (ignoring ledger)"
    else:
        typer.echo("Checking ledger...", nl=False)
        pending = ledger.get_unprocessed(filtered_refs, source, "text")
        count = len(pending)
        verb = "process"
        suffix = ""
        typer.echo(f" {count} to extract")

    typer.echo(f"About to {verb} {count} documents{suffix} against production ({table_name} -> s3://{bucket}/)")

    if count == 0:
        typer.echo("Nothing to do.")
        raise typer.Exit()

    if not yes and not typer.confirm("Continue?", default=False):
        typer.echo("Aborted.")
        raise typer.Exit()

    runner = TextExtractionRunner(
        source=s3_source,
        ledger=ledger,
        config=TextExtractionConfig(),
        writer=writer,
        metadata=metadata,
        filters=filters,
        force=force,
    )
    result = runner.run()
    _report_result(result)


def _report_result(result) -> None:
    """Print a summary of a TextExtractionResult."""
    typer.echo(f"Total:     {result.total}")
    if result.filtered_out:
        typer.echo(f"Filtered:  {result.filtered_out}")
    typer.echo(f"Processed: {result.processed}")
    typer.echo(f"Skipped:   {result.skipped}")
    typer.echo(f"Failed:    {result.failed}")
    if result.failed_keys:
        typer.echo(f"Failed keys: {', '.join(result.failed_keys)}")


@agent_app.command("ask")
def agent_ask(
    query: Annotated[str, typer.Option("--query", help="Natural-language question for the agent.")],
    department: Annotated[str | None, typer.Option("--department", help="Department to scope the query to.")] = None,
):
    from dia.agent import runtime
    from dia.agent.report import ReportUploader
    from dia.cli_helpers import current_names
    from dia.naming import Bucket

    response = runtime.ask(department, query, tunnel=True)
    typer.echo(response.output)

    names = current_names()
    uploader = ReportUploader(bucket=names(Bucket.AGENT_REPORTS))
    result = uploader.upload(response)

    typer.echo(f"\nMarkdown report: {result.markdown_download_url}")
    typer.echo(f"Word doc: {result.docx_download_url}")


@agent_app.command("status")
def agent_status():
    from dia.agent import runtime

    result = runtime.check(tunnel=True)
    for component, status in result.items():
        typer.echo(f"{component}: {status}")
    typer.echo("OK" if all(s == "OK" for s in result.values()) else "FAILED")
