"""Tests for dia.cli — CLI entry point."""

from importlib.metadata import version
from unittest.mock import patch

from typer.testing import CliRunner

from dia.cli import app
from dia.pipeline import PipelineResult

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
# extract command
# ---------------------------------------------------------------------------


def test_extract_unknown_source():
    result = runner.invoke(app, ["extract", "--source", "nonexistent-source"])

    assert result.exit_code == 1
    assert "Unknown source" in result.output


def test_extract_success(tmp_path):
    mock_result = PipelineResult(
        total=5,
        processed=3,
        skipped=2,
        failed=0,
        filtered_out=0,
        failed_keys=[],
        duration_seconds=1.5,
    )

    with (
        patch("dia.sources.known.get_source"),
        patch("dia.sources.s3.S3DocumentSource"),
        patch("dia.pipeline.PipelineRunner") as mock_runner_cls,
    ):
        mock_runner_cls.return_value.run.return_value = mock_result

        result = runner.invoke(app, ["extract", "--source", "test-source", "--log-dir", str(tmp_path)])

    assert result.exit_code == 0
    assert "Total documents:  5" in result.output
    assert "Processed:        3" in result.output
    assert "Skipped:          2" in result.output
    assert "Failed:           0" in result.output
    assert "Duration:         1.5s" in result.output


def test_extract_with_failures_exits_nonzero(tmp_path):
    mock_result = PipelineResult(
        total=3,
        processed=1,
        skipped=0,
        failed=2,
        filtered_out=0,
        failed_keys=["docs/bad1.pdf", "docs/bad2.pdf"],
        duration_seconds=2.0,
    )

    with (
        patch("dia.sources.known.get_source"),
        patch("dia.sources.s3.S3DocumentSource"),
        patch("dia.pipeline.PipelineRunner") as mock_runner_cls,
    ):
        mock_runner_cls.return_value.run.return_value = mock_result

        result = runner.invoke(app, ["extract", "--source", "test-source", "--log-dir", str(tmp_path)])

    assert result.exit_code == 1
    assert "Failed documents:" in result.output
    assert "docs/bad1.pdf" in result.output
    assert "docs/bad2.pdf" in result.output


def test_extract_passes_log_dir_to_runner(tmp_path):
    mock_result = PipelineResult(total=0, processed=0, skipped=0, failed=0, duration_seconds=0.1)

    with (
        patch("dia.sources.known.get_source"),
        patch("dia.sources.s3.S3DocumentSource"),
        patch("dia.pipeline.PipelineRunner") as mock_runner_cls,
    ):
        mock_runner_cls.return_value.run.return_value = mock_result

        runner.invoke(app, ["extract", "--source", "test-source", "--log-dir", str(tmp_path)])

    mock_runner_cls.assert_called_once()
    assert mock_runner_cls.call_args.kwargs["log_dir"] == str(tmp_path)
