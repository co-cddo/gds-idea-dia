"""Tests for dia.cli — CLI entry point."""

from importlib.metadata import version

from typer.testing import CliRunner

from dia.cli import app

runner = CliRunner()


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
