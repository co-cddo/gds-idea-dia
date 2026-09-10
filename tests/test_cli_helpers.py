"""Tests for dia.cli_helpers — environment/resource name resolution."""

from gds_idea_cdk_constructs import DeploymentEnvironment

from dia import cli_helpers


def test_resolve_text_output_bucket(monkeypatch):
    monkeypatch.setattr(cli_helpers, "detect_environment", lambda: DeploymentEnvironment.DEVELOPMENT)
    assert cli_helpers.resolve_text_output_bucket() == "gds-idea-dia-text-extracted-dev"


def test_resolve_chunks_bucket(monkeypatch):
    monkeypatch.setattr(cli_helpers, "detect_environment", lambda: DeploymentEnvironment.DEVELOPMENT)
    assert cli_helpers.resolve_chunks_bucket() == "gds-idea-dia-chunks-dev"


def test_resolve_ledger_table(monkeypatch):
    monkeypatch.setattr(cli_helpers, "detect_environment", lambda: DeploymentEnvironment.DEVELOPMENT)
    assert cli_helpers.resolve_ledger_table() == "dia-ledger-dev"
