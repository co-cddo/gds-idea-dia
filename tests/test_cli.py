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


def test_ledger_clone_writes_local_file(tmp_path):
    mock_records = [
        {
            "document_key": "text#gats-business-cases#docs/a.pdf#v1",
            "source_name": "gats-business-cases",
            "processed_at": "2026-07-20T10:00:00+00:00",
            "code_version": "0.1.13",
            "department": None,
        },
        {
            "document_key": "text#gats-business-cases#docs/b.pdf#v1",
            "source_name": "gats-business-cases",
            "processed_at": "2026-07-20T10:01:00+00:00",
            "code_version": "0.1.13",
            "department": None,
        },
    ]
    to_path = tmp_path / "cloned.ledger.json"

    with (
        patch("dia.cli_helpers.resolve_ledger_table", return_value="dia-ledger-dev"),
        patch("dia.ledger.dynamodb.DynamoDBLedger") as mock_cls,
    ):
        mock_cls.return_value.list_records.return_value = mock_records

        result = runner.invoke(
            app,
            ["ledger", "clone", "--source", "gats-business-cases", "--to", str(to_path)],
        )

    assert result.exit_code == 0
    assert "Cloned 2 records" in result.output
    assert to_path.exists()

    import json

    data = json.loads(to_path.read_text())
    assert "text#gats-business-cases#docs/a.pdf#v1" in data
    assert data["text#gats-business-cases#docs/a.pdf#v1"]["source_name"] == "gats-business-cases"
    assert "document_key" not in data["text#gats-business-cases#docs/a.pdf#v1"]


def test_ledger_clone_creates_parent_directories(tmp_path):
    mock_records = [
        {
            "document_key": "text#src#a.pdf#v1",
            "source_name": "src",
            "processed_at": "2026-07-20T10:00:00+00:00",
            "code_version": "0.1.13",
        },
    ]
    to_path = tmp_path / "nested" / "dir" / "ledger.json"

    with (
        patch("dia.cli_helpers.resolve_ledger_table", return_value="dia-ledger-dev"),
        patch("dia.ledger.dynamodb.DynamoDBLedger") as mock_cls,
    ):
        mock_cls.return_value.list_records.return_value = mock_records

        result = runner.invoke(app, ["ledger", "clone", "--source", "src", "--to", str(to_path)])

    assert result.exit_code == 0
    assert to_path.exists()


def test_ledger_clone_no_records():
    with (
        patch("dia.cli_helpers.resolve_ledger_table", return_value="dia-ledger-dev"),
        patch("dia.ledger.dynamodb.DynamoDBLedger") as mock_cls,
    ):
        mock_cls.return_value.list_records.return_value = []

        result = runner.invoke(app, ["ledger", "clone", "--source", "empty-source", "--to", "./nowhere.json"])

    assert result.exit_code == 0
    assert "No records found" in result.output


def test_ledger_clone_output_can_be_used_by_json_file_ledger(tmp_path):
    """The cloned file should be directly loadable by JsonFileLedger."""
    mock_records = [
        {
            "document_key": "text#src#a.pdf#v1",
            "source_name": "src",
            "processed_at": "2026-07-20T10:00:00+00:00",
            "code_version": "0.1.13",
            "department": None,
        },
    ]
    to_path = tmp_path / "ledger.json"

    with (
        patch("dia.cli_helpers.resolve_ledger_table", return_value="dia-ledger-dev"),
        patch("dia.ledger.dynamodb.DynamoDBLedger") as mock_cls,
    ):
        mock_cls.return_value.list_records.return_value = mock_records

        runner.invoke(app, ["ledger", "clone", "--source", "src", "--to", str(to_path)])

    from dia.ledger.file import JsonFileLedger
    from dia.types import DocumentReference

    loaded = JsonFileLedger(to_path)
    ref = DocumentReference(key="a.pdf", content_type="application/pdf", version="v1")
    result = loaded.get_unprocessed([ref], "src", "text")

    assert result == []  # already marked processed via the clone


# ---------------------------------------------------------------------------
# extract-text
# ---------------------------------------------------------------------------


def test_extract_text_unknown_source():
    result = runner.invoke(app, ["extract-text", "--source", "nonexistent"])

    assert result.exit_code == 1
    assert "Unknown source" in result.output


def test_extract_text_output_and_live_both_set_errors():
    with patch("dia.sources.known.get_source"), patch("dia.sources.s3.S3DocumentSource"):
        result = runner.invoke(app, ["extract-text", "--source", "test", "--output", "./x", "--live"])

    assert result.exit_code == 1
    assert "not both" in result.output


def test_extract_text_dry_run_reports_counts(tmp_path):
    """No --output, no --live: dry run against the DynamoDB ledger."""
    from dia.types import DocumentReference

    refs = [
        DocumentReference(key="a.pdf", content_type="application/pdf", version="v1"),
        DocumentReference(key="b.pdf", content_type="application/pdf", version="v1"),
        DocumentReference(key="c.pdf", content_type="application/pdf", version="v1"),
    ]

    with (
        patch("dia.sources.known.get_source"),
        patch("dia.sources.s3.S3DocumentSource") as mock_source_cls,
        patch("dia.cli_helpers.resolve_ledger_table", return_value="dia-ledger-dev"),
        patch("dia.ledger.dynamodb.DynamoDBLedger") as mock_ledger_cls,
    ):
        mock_source = mock_source_cls.return_value
        mock_source.list_documents.return_value = refs
        mock_source.data_source.document_type = "business_case"
        mock_source.data_source.bucket = "test-bucket"

        mock_ledger_cls.return_value.get_unprocessed.return_value = refs[:1]

        result = runner.invoke(app, ["extract-text", "--source", "test-source"])

    assert result.exit_code == 0
    assert "Total documents:    3" in result.output
    assert "Already processed:  2" in result.output
    assert "Would process:      1" in result.output
    # Dry run must not import the runner or touch output/ledger writes
    mock_source.load_document.assert_not_called()


def test_extract_text_local_mode_uses_json_file_ledger(tmp_path):
    from dia.pipeline import TextExtractionResult

    mock_result = TextExtractionResult(total=5, processed=3, skipped=2, failed=0, filtered_out=0, duration_seconds=1.2)
    output_dir = tmp_path / "output"

    with (
        patch("dia.sources.known.get_source"),
        patch("dia.sources.s3.S3DocumentSource"),
        patch("dia.pipeline.TextExtractionRunner") as mock_runner_cls,
    ):
        mock_runner_cls.return_value.run.return_value = mock_result

        result = runner.invoke(
            app,
            [
                "extract-text",
                "--source",
                "test",
                "--output",
                str(output_dir),
                "--log-dir",
                str(tmp_path / "logs"),
            ],
        )

    assert result.exit_code == 0
    assert f"ledger={output_dir / '.ledger.json'}" in result.output
    assert "Processed:        3" in result.output

    # Runner constructed with output_dir, not output_bucket
    call_kwargs = mock_runner_cls.call_args.kwargs
    assert call_kwargs["output_dir"] == output_dir
    assert "output_bucket" not in call_kwargs


def test_extract_text_live_mode_uses_dynamodb_and_s3(tmp_path):
    from dia.pipeline import TextExtractionResult

    mock_result = TextExtractionResult(total=0, processed=0, skipped=0, failed=0, filtered_out=0, duration_seconds=0.1)

    with (
        patch("dia.sources.known.get_source"),
        patch("dia.sources.s3.S3DocumentSource"),
        patch("dia.cli_helpers.resolve_ledger_table", return_value="dia-ledger-dev"),
        patch(
            "dia.cli_helpers.resolve_text_output_bucket",
            return_value="gds-idea-dia-text-extracted-dev",
        ),
        patch("dia.ledger.dynamodb.DynamoDBLedger"),
        patch("dia.pipeline.TextExtractionRunner") as mock_runner_cls,
    ):
        mock_runner_cls.return_value.run.return_value = mock_result

        result = runner.invoke(app, ["extract-text", "--source", "test", "--live", "--log-dir", str(tmp_path)])

    assert result.exit_code == 0
    assert "output=gds-idea-dia-text-extracted-dev" in result.output
    assert "ledger=dia-ledger-dev" in result.output

    call_kwargs = mock_runner_cls.call_args.kwargs
    assert call_kwargs["output_bucket"] == "gds-idea-dia-text-extracted-dev"
    assert "output_dir" not in call_kwargs


def test_extract_text_local_mode_failure_exits_nonzero(tmp_path):
    from dia.pipeline import TextExtractionResult

    mock_result = TextExtractionResult(
        total=2,
        processed=1,
        skipped=0,
        failed=1,
        filtered_out=0,
        failed_keys=["docs/bad.pdf"],
        duration_seconds=0.5,
    )

    with (
        patch("dia.sources.known.get_source"),
        patch("dia.sources.s3.S3DocumentSource"),
        patch("dia.pipeline.TextExtractionRunner") as mock_runner_cls,
    ):
        mock_runner_cls.return_value.run.return_value = mock_result

        result = runner.invoke(
            app,
            [
                "extract-text",
                "--source",
                "test",
                "--output",
                str(tmp_path / "output"),
                "--log-dir",
                str(tmp_path / "logs"),
            ],
        )

    assert result.exit_code == 1
    assert "Failed documents:" in result.output
    assert "docs/bad.pdf" in result.output
