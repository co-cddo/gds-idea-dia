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
