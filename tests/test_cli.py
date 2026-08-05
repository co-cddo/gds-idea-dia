"""Tests for dia.cli — CLI entry point."""

from importlib.metadata import version
from unittest.mock import patch

from typer.testing import CliRunner

from dia.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


def test_version_flag():
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert version("dia") in result.output


def test_version_short_flag():
    result = runner.invoke(app, ["-v"])

    assert result.exit_code == 0
    assert "dia" in result.output


def test_no_args_shows_help():
    result = runner.invoke(app, [])

    assert result.exit_code == 0 or result.exit_code == 2
    assert "Department Intelligence Agent" in result.output


def test_help_flag():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Print version and exit" in result.output


# ---------------------------------------------------------------------------
# ledger list
# ---------------------------------------------------------------------------


def test_ledger_list_shows_records():
    mock_records = [
        {
            "document_key": "test-source#docs/a.pdf#v1",
            "source_name": "test-source",
            "processed_at": "2026-07-20T10:00:00+00:00",
            "code_version": "0.1.9",
        },
        {
            "document_key": "test-source#docs/b.pdf#v2",
            "source_name": "test-source",
            "processed_at": "2026-07-20T10:01:00+00:00",
            "code_version": "0.1.9",
        },
    ]

    with (
        patch("dia.cli_helpers.resolve_ledger_table", return_value="dia-ledger-dev"),
        patch("dia.ledger.dynamodb.DynamoDBLedger") as mock_cls,
    ):
        mock_cls.return_value.list_records.return_value = mock_records

        result = runner.invoke(app, ["ledger", "list", "--source", "test-source"])

    assert result.exit_code == 0
    assert "Source: test-source" in result.output
    assert "Count:  2" in result.output
    assert "docs/a.pdf" in result.output
    assert "docs/b.pdf" in result.output


def test_ledger_list_empty_source():
    with (
        patch("dia.cli_helpers.resolve_ledger_table", return_value="dia-ledger-dev"),
        patch("dia.ledger.dynamodb.DynamoDBLedger") as mock_cls,
    ):
        mock_cls.return_value.list_records.return_value = []

        result = runner.invoke(app, ["ledger", "list", "--source", "empty-source"])

    assert result.exit_code == 0
    assert "No records found" in result.output


# ---------------------------------------------------------------------------
# ledger clear
# ---------------------------------------------------------------------------


def test_ledger_clear_dry_run():
    mock_records = [
        {"document_key": "src#a.pdf#v1", "source_name": "src"},
        {"document_key": "src#b.pdf#v1", "source_name": "src"},
    ]

    with (
        patch("dia.cli_helpers.resolve_ledger_table", return_value="dia-ledger-dev"),
        patch("dia.ledger.dynamodb.DynamoDBLedger") as mock_cls,
    ):
        mock_cls.return_value.list_records.return_value = mock_records

        result = runner.invoke(app, ["ledger", "clear", "--source", "src", "--dry-run"])

    assert result.exit_code == 0
    assert "Would delete 2 records" in result.output
    assert "Run without --dry-run" in result.output


def test_ledger_clear_source():
    with (
        patch("dia.cli_helpers.resolve_ledger_table", return_value="dia-ledger-dev"),
        patch("dia.ledger.dynamodb.DynamoDBLedger") as mock_cls,
    ):
        mock_cls.return_value.clear.return_value = 5

        result = runner.invoke(app, ["ledger", "clear", "--source", "test-source"])

    assert result.exit_code == 0
    assert "Deleted 5 records" in result.output
    assert "test-source" in result.output


def test_ledger_clear_all():
    with (
        patch("dia.cli_helpers.resolve_ledger_table", return_value="dia-ledger-dev"),
        patch("dia.ledger.dynamodb.DynamoDBLedger") as mock_cls,
    ):
        mock_cls.return_value.clear_all.return_value = 12

        result = runner.invoke(app, ["ledger", "clear", "--all"])

    assert result.exit_code == 0
    assert "Deleted 12 records" in result.output


def test_ledger_clear_all_dry_run():
    mock_records = [
        {"document_key": "text#source-a#a.pdf#v1", "source_name": "source-a"},
        {"document_key": "text#source-b#b.pdf#v1", "source_name": "source-b"},
    ]

    with (
        patch("dia.cli_helpers.resolve_ledger_table", return_value="dia-ledger-dev"),
        patch("dia.ledger.dynamodb.DynamoDBLedger") as mock_cls,
    ):
        mock_cls.return_value.list_all_records.return_value = mock_records
        mock_cls.return_value.list_records.side_effect = lambda source: [
            r for r in mock_records if r["source_name"] == source
        ]

        result = runner.invoke(app, ["ledger", "clear", "--all", "--dry-run"])

    assert result.exit_code == 0
    assert "Would delete 2 records" in result.output
    assert "Run without --dry-run" in result.output


def test_ledger_clear_requires_source_or_all():
    with (
        patch("dia.cli_helpers.resolve_ledger_table", return_value="dia-ledger-dev"),
        patch("dia.ledger.dynamodb.DynamoDBLedger"),
    ):
        result = runner.invoke(app, ["ledger", "clear"])

    assert result.exit_code == 1
    assert "Provide --source" in result.output


# ---------------------------------------------------------------------------
# ledger clone
# ---------------------------------------------------------------------------


def test_ledger_clone_writes_records_to_file(tmp_path):
    mock_records = [
        {
            "document_key": "text#source-a#docs/a.pdf#v1",
            "source_name": "source-a",
            "processed_at": "2026-07-20T10:00:00+00:00",
            "code_version": "0.1.9",
        },
        {
            "document_key": "text#source-b#docs/b.pdf#v2",
            "source_name": "source-b",
            "processed_at": "2026-07-20T10:01:00+00:00",
            "code_version": "0.1.9",
        },
    ]

    target = str(tmp_path / "ledger.json")

    with (
        patch("dia.cli_helpers.resolve_ledger_table", return_value="dia-ledger-dev"),
        patch("dia.ledger.dynamodb.DynamoDBLedger") as mock_cls,
    ):
        mock_cls.return_value.list_all_records.return_value = mock_records

        result = runner.invoke(app, ["ledger", "clone", "--to", target])

    assert result.exit_code == 0
    assert "Cloned 2 records" in result.output

    # Verify the file is valid JsonFileLedger format
    import json

    data = json.loads((tmp_path / "ledger.json").read_text())
    assert "text#source-a#docs/a.pdf#v1" in data
    assert "text#source-b#docs/b.pdf#v2" in data
    # document_key should NOT be stored inside the record dict
    assert "document_key" not in data["text#source-a#docs/a.pdf#v1"]


def test_ledger_clone_default_path(tmp_path, monkeypatch):
    """With no --to, defaults to output/ledger.json (relative to cwd)."""
    monkeypatch.chdir(tmp_path)

    mock_records = [
        {
            "document_key": "text#src#a.pdf#v1",
            "source_name": "src",
            "processed_at": "2026-07-20T10:00:00+00:00",
            "code_version": "0.1.9",
        },
    ]

    with (
        patch("dia.cli_helpers.resolve_ledger_table", return_value="dia-ledger-dev"),
        patch("dia.ledger.dynamodb.DynamoDBLedger") as mock_cls,
    ):
        mock_cls.return_value.list_all_records.return_value = mock_records

        result = runner.invoke(app, ["ledger", "clone"])

    assert result.exit_code == 0
    assert "Cloned 1 records" in result.output
    assert "output/ledger.json" in result.output
    assert (tmp_path / "output" / "ledger.json").exists()


def test_ledger_clone_overwrites_existing_file(tmp_path):
    """Cloning replaces the target file entirely — it does not merge."""
    import json

    target = tmp_path / "ledger.json"
    # Pre-populate with a stale local record that is NOT in DynamoDB
    existing = {
        "graph#stale-source#report.pdf#v1": {
            "source_name": "stale-source",
            "processed_at": "2026-07-01T00:00:00+00:00",
            "code_version": "0.1.0",
        }
    }
    target.write_text(json.dumps(existing))

    mock_records = [
        {
            "document_key": "text#my-source#docs/a.pdf#v1",
            "source_name": "my-source",
            "processed_at": "2026-07-20T10:00:00+00:00",
            "code_version": "0.1.9",
        },
    ]

    with (
        patch("dia.cli_helpers.resolve_ledger_table", return_value="dia-ledger-dev"),
        patch("dia.ledger.dynamodb.DynamoDBLedger") as mock_cls,
    ):
        mock_cls.return_value.list_all_records.return_value = mock_records

        result = runner.invoke(app, ["ledger", "clone", "--to", str(target)])

    assert result.exit_code == 0
    assert "Cloned 1 records" in result.output

    data = json.loads(target.read_text())
    # Stale record is gone, only the freshly cloned record remains
    assert "graph#stale-source#report.pdf#v1" not in data
    assert "text#my-source#docs/a.pdf#v1" in data


def test_ledger_clone_empty_table():
    with (
        patch("dia.cli_helpers.resolve_ledger_table", return_value="dia-ledger-dev"),
        patch("dia.ledger.dynamodb.DynamoDBLedger") as mock_cls,
    ):
        mock_cls.return_value.list_all_records.return_value = []

        result = runner.invoke(app, ["ledger", "clone", "--to", "/tmp/x.json"])

    assert result.exit_code == 0
    assert "No records found" in result.output


def test_ledger_clone_creates_parent_directories(tmp_path):
    mock_records = [
        {
            "document_key": "text#src#a.pdf#v1",
            "source_name": "src",
            "processed_at": "2026-07-20T10:00:00+00:00",
            "code_version": "0.1.9",
        },
    ]

    target = str(tmp_path / "nested" / "dir" / "ledger.json")

    with (
        patch("dia.cli_helpers.resolve_ledger_table", return_value="dia-ledger-dev"),
        patch("dia.ledger.dynamodb.DynamoDBLedger") as mock_cls,
    ):
        mock_cls.return_value.list_all_records.return_value = mock_records

        result = runner.invoke(app, ["ledger", "clone", "--to", target])

    assert result.exit_code == 0
    assert "Cloned 1 records" in result.output

    import json
    from pathlib import Path

    data = json.loads(Path(target).read_text())
    assert "text#src#a.pdf#v1" in data


# ---------------------------------------------------------------------------
# extract-text
# ---------------------------------------------------------------------------


def _make_data_source(prefix="docs/"):
    from dia.document_types import DocumentType
    from dia.types import DataSource

    return DataSource(
        name="test-source",
        document_type=DocumentType.BUSINESS_CASE,
        bucket="test-bucket",
        prefix=prefix,
    )


def _make_refs(n: int):
    from dia.types import DocumentReference

    return [
        DocumentReference(key=f"docs/doc{i}.pdf", content_type="application/pdf", version=f"v{i}") for i in range(n)
    ]


def _make_result(**overrides):
    from dia.pipeline import TextExtractionResult

    defaults = {"total": 3, "processed": 3, "skipped": 0, "failed": 0}
    defaults.update(overrides)
    return TextExtractionResult(**defaults)


def test_extract_text_execute_and_live_mutually_exclusive():
    result = runner.invoke(app, ["extract-text", "--source", "test-source", "--execute", "--live"])

    assert result.exit_code == 1
    assert "mutually exclusive" in result.output


def test_extract_text_inmemory_ledger_requires_execute():
    result = runner.invoke(app, ["extract-text", "--source", "test-source", "--inmemory-ledger"])

    assert result.exit_code == 1
    assert "--inmemory-ledger is only valid with --execute" in result.output


def test_extract_text_unknown_source():
    with patch("dia.sources.known.get_source", side_effect=KeyError("test-source")):
        result = runner.invoke(app, ["extract-text", "--source", "unknown-source"])

    assert result.exit_code == 1
    assert "Unknown source" in result.output


def test_extract_text_preview_shows_counts():
    data_source = _make_data_source()
    refs = _make_refs(5)

    with (
        patch("dia.sources.known.get_source", return_value=data_source),
        patch("dia.sources.s3.S3DocumentSource") as mock_source_cls,
        patch("dia.metadata.load_metadata", return_value=None),
        patch("dia.ledger.file.JsonFileLedger") as mock_ledger_cls,
    ):
        mock_source_cls.return_value.list_documents.return_value = refs
        mock_ledger_cls.return_value.get_unprocessed.return_value = refs[:2]

        result = runner.invoke(app, ["extract-text", "--source", "test-source"])

    assert result.exit_code == 0
    assert "Listing documents... 5 found" in result.output
    assert "Checking ledger (output/ledger.json)... 3 already done, 2 to extract" in result.output
    assert "--execute" in result.output
    assert "--live" in result.output


def test_extract_text_preview_suggests_ledger_clone_when_nothing_done():
    data_source = _make_data_source()
    refs = _make_refs(5)

    with (
        patch("dia.sources.known.get_source", return_value=data_source),
        patch("dia.sources.s3.S3DocumentSource") as mock_source_cls,
        patch("dia.metadata.load_metadata", return_value=None),
        patch("dia.ledger.file.JsonFileLedger") as mock_ledger_cls,
    ):
        mock_source_cls.return_value.list_documents.return_value = refs
        mock_ledger_cls.return_value.get_unprocessed.return_value = refs

        result = runner.invoke(app, ["extract-text", "--source", "test-source"])

    assert result.exit_code == 0
    assert "Tip: run `dia ledger clone` to seed from production." in result.output


def test_extract_text_preview_with_force_ignores_ledger():
    data_source = _make_data_source()
    refs = _make_refs(4)

    with (
        patch("dia.sources.known.get_source", return_value=data_source),
        patch("dia.sources.s3.S3DocumentSource") as mock_source_cls,
        patch("dia.metadata.load_metadata", return_value=None),
        patch("dia.ledger.file.JsonFileLedger") as mock_ledger_cls,
    ):
        mock_source_cls.return_value.list_documents.return_value = refs

        result = runner.invoke(app, ["extract-text", "--source", "test-source", "--force"])

    assert result.exit_code == 0
    assert "To extract: 4 (--force: ignoring ledger)" in result.output
    # Ledger should never be consulted when --force is set
    mock_ledger_cls.return_value.get_unprocessed.assert_not_called()


def test_extract_text_departments_without_metadata_errors():
    data_source = _make_data_source()
    refs = _make_refs(3)

    with (
        patch("dia.sources.known.get_source", return_value=data_source),
        patch("dia.sources.s3.S3DocumentSource") as mock_source_cls,
        patch("dia.metadata.load_metadata", return_value=None),
    ):
        mock_source_cls.return_value.list_documents.return_value = refs

        result = runner.invoke(app, ["extract-text", "--source", "test-source", "--departments", "HMRC"])

    assert result.exit_code == 1
    assert "does not support department filtering" in result.output


def test_extract_text_departments_filters_refs():
    from dia.metadata.models import DocumentMetadata
    from dia.metadata.provider import MetadataProvider

    data_source = _make_data_source()
    refs = _make_refs(3)
    lookup = {
        "docs/doc0.pdf": DocumentMetadata(department="HMRC"),
        "docs/doc1.pdf": DocumentMetadata(department="DfE"),
    }
    metadata = MetadataProvider(lookup)

    with (
        patch("dia.sources.known.get_source", return_value=data_source),
        patch("dia.sources.s3.S3DocumentSource") as mock_source_cls,
        patch("dia.metadata.load_metadata", return_value=metadata),
        patch("dia.ledger.file.JsonFileLedger") as mock_ledger_cls,
    ):
        mock_source_cls.return_value.list_documents.return_value = refs
        mock_ledger_cls.return_value.get_unprocessed.side_effect = lambda r, *_: r

        result = runner.invoke(app, ["extract-text", "--source", "test-source", "--departments", "HMRC"])

    assert result.exit_code == 0
    assert "Listing documents... 3 found" in result.output
    assert "After department filter: 1 (removed 2)" in result.output


def test_extract_text_shows_metadata_load_progress():
    from dia.metadata.models import DocumentMetadata
    from dia.metadata.provider import MetadataProvider

    data_source = _make_data_source()
    refs = _make_refs(3)
    metadata = MetadataProvider({"docs/doc0.pdf": DocumentMetadata(department="HMRC")})

    with (
        patch("dia.sources.known.get_source", return_value=data_source),
        patch("dia.sources.s3.S3DocumentSource") as mock_source_cls,
        patch("dia.metadata.load_metadata", return_value=metadata),
        patch("dia.ledger.file.JsonFileLedger") as mock_ledger_cls,
    ):
        mock_source_cls.return_value.list_documents.return_value = refs
        mock_ledger_cls.return_value.get_unprocessed.return_value = refs

        result = runner.invoke(app, ["extract-text", "--source", "test-source"])

    assert result.exit_code == 0
    assert "Loading metadata... 1 entries loaded" in result.output


def test_extract_text_shows_no_metadata_configured():
    data_source = _make_data_source()
    refs = _make_refs(2)

    with (
        patch("dia.sources.known.get_source", return_value=data_source),
        patch("dia.sources.s3.S3DocumentSource") as mock_source_cls,
        patch("dia.metadata.load_metadata", return_value=None),
        patch("dia.ledger.file.JsonFileLedger") as mock_ledger_cls,
    ):
        mock_source_cls.return_value.list_documents.return_value = refs
        mock_ledger_cls.return_value.get_unprocessed.return_value = refs

        result = runner.invoke(app, ["extract-text", "--source", "test-source"])

    assert result.exit_code == 0
    assert "Loading metadata... none configured" in result.output


def test_extract_text_execute_uses_local_writer_and_file_ledger():
    data_source = _make_data_source()
    refs = _make_refs(3)

    with (
        patch("dia.sources.known.get_source", return_value=data_source),
        patch("dia.sources.s3.S3DocumentSource") as mock_source_cls,
        patch("dia.metadata.load_metadata", return_value=None),
        patch("dia.ledger.file.JsonFileLedger") as mock_ledger_cls,
        patch("dia.pipeline.TextExtractionRunner") as mock_runner_cls,
    ):
        mock_source_cls.return_value.list_documents.return_value = refs
        mock_runner_cls.return_value.run.return_value = _make_result()

        result = runner.invoke(app, ["extract-text", "--source", "test-source", "--execute"])

    assert result.exit_code == 0
    mock_ledger_cls.assert_called_once_with("output/ledger.json")
    _, kwargs = mock_runner_cls.call_args
    assert kwargs["force"] is False
    assert "Processed: 3" in result.output


def test_extract_text_execute_inmemory_ledger():
    data_source = _make_data_source()
    refs = _make_refs(2)

    with (
        patch("dia.sources.known.get_source", return_value=data_source),
        patch("dia.sources.s3.S3DocumentSource") as mock_source_cls,
        patch("dia.metadata.load_metadata", return_value=None),
        patch("dia.ledger.memory.InMemoryLedger") as mock_ledger_cls,
        patch("dia.ledger.file.JsonFileLedger") as mock_file_ledger_cls,
        patch("dia.pipeline.TextExtractionRunner") as mock_runner_cls,
    ):
        mock_source_cls.return_value.list_documents.return_value = refs
        mock_runner_cls.return_value.run.return_value = _make_result(total=2, processed=2)

        result = runner.invoke(app, ["extract-text", "--source", "test-source", "--execute", "--inmemory-ledger"])

    assert result.exit_code == 0
    mock_ledger_cls.assert_called_once()
    mock_file_ledger_cls.assert_not_called()


def test_extract_text_execute_force_passed_to_runner():
    data_source = _make_data_source()
    refs = _make_refs(2)

    with (
        patch("dia.sources.known.get_source", return_value=data_source),
        patch("dia.sources.s3.S3DocumentSource") as mock_source_cls,
        patch("dia.metadata.load_metadata", return_value=None),
        patch("dia.ledger.file.JsonFileLedger"),
        patch("dia.pipeline.TextExtractionRunner") as mock_runner_cls,
    ):
        mock_source_cls.return_value.list_documents.return_value = refs
        mock_runner_cls.return_value.run.return_value = _make_result(total=2, processed=2)

        result = runner.invoke(app, ["extract-text", "--source", "test-source", "--execute", "--force"])

    assert result.exit_code == 0
    _, kwargs = mock_runner_cls.call_args
    assert kwargs["force"] is True


def test_extract_text_live_prompts_and_aborts_on_no():
    data_source = _make_data_source()
    refs = _make_refs(3)

    with (
        patch("dia.sources.known.get_source", return_value=data_source),
        patch("dia.sources.s3.S3DocumentSource") as mock_source_cls,
        patch("dia.metadata.load_metadata", return_value=None),
        patch("dia.cli_helpers.resolve_ledger_table", return_value="dia-ledger-prod"),
        patch("dia.cli_helpers.resolve_text_output_bucket", return_value="dia-text-extracted-prod"),
        patch("dia.ledger.dynamodb.DynamoDBLedger") as mock_ledger_cls,
        patch("dia.writers.s3.S3OutputWriter"),
        patch("dia.pipeline.TextExtractionRunner") as mock_runner_cls,
    ):
        mock_source_cls.return_value.list_documents.return_value = refs
        mock_ledger_cls.return_value.get_unprocessed.return_value = refs

        result = runner.invoke(app, ["extract-text", "--source", "test-source", "--live"], input="n\n")

    assert result.exit_code == 0
    assert "About to process 3 documents" in result.output
    assert "Aborted." in result.output
    mock_runner_cls.return_value.run.assert_not_called()


def test_extract_text_live_yes_skips_confirmation():
    data_source = _make_data_source()
    refs = _make_refs(2)

    with (
        patch("dia.sources.known.get_source", return_value=data_source),
        patch("dia.sources.s3.S3DocumentSource") as mock_source_cls,
        patch("dia.metadata.load_metadata", return_value=None),
        patch("dia.cli_helpers.resolve_ledger_table", return_value="dia-ledger-prod"),
        patch("dia.cli_helpers.resolve_text_output_bucket", return_value="dia-text-extracted-prod"),
        patch("dia.ledger.dynamodb.DynamoDBLedger") as mock_ledger_cls,
        patch("dia.writers.s3.S3OutputWriter"),
        patch("dia.pipeline.TextExtractionRunner") as mock_runner_cls,
    ):
        mock_source_cls.return_value.list_documents.return_value = refs
        mock_ledger_cls.return_value.get_unprocessed.return_value = refs
        mock_runner_cls.return_value.run.return_value = _make_result(total=2, processed=2)

        result = runner.invoke(app, ["extract-text", "--source", "test-source", "--live", "--yes"])

    assert result.exit_code == 0
    mock_runner_cls.return_value.run.assert_called_once()
    assert "Processed: 2" in result.output


def test_extract_text_live_force_shows_reprocess_warning():
    data_source = _make_data_source()
    refs = _make_refs(5)

    with (
        patch("dia.sources.known.get_source", return_value=data_source),
        patch("dia.sources.s3.S3DocumentSource") as mock_source_cls,
        patch("dia.metadata.load_metadata", return_value=None),
        patch("dia.cli_helpers.resolve_ledger_table", return_value="dia-ledger-prod"),
        patch("dia.cli_helpers.resolve_text_output_bucket", return_value="dia-text-extracted-prod"),
        patch("dia.ledger.dynamodb.DynamoDBLedger") as mock_ledger_cls,
        patch("dia.writers.s3.S3OutputWriter"),
        patch("dia.pipeline.TextExtractionRunner") as mock_runner_cls,
    ):
        mock_source_cls.return_value.list_documents.return_value = refs
        mock_runner_cls.return_value.run.return_value = _make_result(total=5, processed=5)

        result = runner.invoke(app, ["extract-text", "--source", "test-source", "--live", "--force", "--yes"])

    assert result.exit_code == 0
    assert "About to REPROCESS 5 documents (ignoring ledger)" in result.output
    mock_ledger_cls.return_value.get_unprocessed.assert_not_called()


def test_extract_text_live_nothing_to_do():
    data_source = _make_data_source()
    refs = _make_refs(2)

    with (
        patch("dia.sources.known.get_source", return_value=data_source),
        patch("dia.sources.s3.S3DocumentSource") as mock_source_cls,
        patch("dia.metadata.load_metadata", return_value=None),
        patch("dia.cli_helpers.resolve_ledger_table", return_value="dia-ledger-prod"),
        patch("dia.cli_helpers.resolve_text_output_bucket", return_value="dia-text-extracted-prod"),
        patch("dia.ledger.dynamodb.DynamoDBLedger") as mock_ledger_cls,
        patch("dia.writers.s3.S3OutputWriter"),
        patch("dia.pipeline.TextExtractionRunner") as mock_runner_cls,
    ):
        mock_source_cls.return_value.list_documents.return_value = refs
        mock_ledger_cls.return_value.get_unprocessed.return_value = []

        result = runner.invoke(app, ["extract-text", "--source", "test-source", "--live"])

    assert result.exit_code == 0
    assert "Nothing to do." in result.output
    mock_runner_cls.return_value.run.assert_not_called()


def test_extract_text_reports_failed_keys():
    data_source = _make_data_source()
    refs = _make_refs(2)

    with (
        patch("dia.sources.known.get_source", return_value=data_source),
        patch("dia.sources.s3.S3DocumentSource") as mock_source_cls,
        patch("dia.metadata.load_metadata", return_value=None),
        patch("dia.ledger.file.JsonFileLedger"),
        patch("dia.pipeline.TextExtractionRunner") as mock_runner_cls,
    ):
        mock_source_cls.return_value.list_documents.return_value = refs
        mock_runner_cls.return_value.run.return_value = _make_result(
            total=2, processed=1, failed=1, failed_keys=["docs/doc1.pdf"]
        )

        result = runner.invoke(app, ["extract-text", "--source", "test-source", "--execute"])

    assert result.exit_code == 0
    assert "Failed:    1" in result.output
    assert "Failed keys: docs/doc1.pdf" in result.output
