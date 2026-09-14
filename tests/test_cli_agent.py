"""Tests for the `dia agent` CLI subcommands (ask, status) — CLI wiring only.

runtime.ask()/runtime.check() are fully mocked; these tests only assert that
the CLI parses args correctly, passes them through, and renders the result.
"""

from unittest.mock import patch

from typer.testing import CliRunner

from dia.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# dia agent ask
# ---------------------------------------------------------------------------


def test_agent_ask_passes_query_and_department_through_with_tunnel_true():
    """ask has no --tunnel CLI option - it always calls runtime.ask() with
    tunnel=True (hardcoded), since ask() needs Neptune/AOSS access to succeed."""
    with patch("dia.agent.runtime.ask") as mock_ask:
        mock_ask.return_value = "an answer"

        result = runner.invoke(
            app,
            ["agent", "ask", "--query", "what is the risk?", "--department", "Home Office"],
        )

        assert result.exit_code == 0
        mock_ask.assert_called_once_with("Home Office", "what is the risk?", tunnel=True)


def test_agent_ask_defaults_department_none():
    with patch("dia.agent.runtime.ask") as mock_ask:
        mock_ask.return_value = "an answer"

        result = runner.invoke(app, ["agent", "ask", "--query", "what is the risk?"])

        assert result.exit_code == 0
        mock_ask.assert_called_once_with(None, "what is the risk?", tunnel=True)


def test_agent_ask_has_no_tunnel_option():
    result = runner.invoke(app, ["agent", "ask", "--help"])

    assert "--tunnel" not in result.output


def test_agent_ask_rejects_tunnel_flag():
    result = runner.invoke(app, ["agent", "ask", "--query", "what is the risk?", "--tunnel"])

    assert result.exit_code != 0


def test_agent_ask_echoes_the_result():
    with patch("dia.agent.runtime.ask") as mock_ask:
        mock_ask.return_value = "an answer"

        result = runner.invoke(app, ["agent", "ask", "--query", "what is the risk?"])

        assert "an answer" in result.output


def test_agent_ask_requires_query():
    result = runner.invoke(app, ["agent", "ask"])

    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# dia agent status
# ---------------------------------------------------------------------------


def test_agent_status_always_calls_check_with_tunnel_true():
    """status has no --tunnel CLI option (removed - it was unreachable/broken:
    default True, no --no-tunnel counterpart). check(tunnel=...) is always
    called with tunnel=True, hardcoded in cli.py."""
    with patch("dia.agent.runtime.check") as mock_check:
        mock_check.return_value = {"tunnel": "OK", "stores": "OK", "mcp_server": "OK"}

        runner.invoke(app, ["agent", "status"])

        mock_check.assert_called_once_with(tunnel=True)


def test_agent_status_has_no_tunnel_option():
    """The --tunnel option was removed from `status` entirely - runtime.check()
    still supports tunnel=False, but only reachable by calling it directly in
    Python (e.g. tests), not from this CLI command."""
    result = runner.invoke(app, ["agent", "status", "--help"])

    assert "--tunnel" not in result.output
    assert "--no-tunnel" not in result.output


def test_agent_status_rejects_tunnel_flag():
    result = runner.invoke(app, ["agent", "status", "--tunnel"])

    assert result.exit_code != 0


def test_agent_status_prints_one_line_per_component():
    with patch("dia.agent.runtime.check") as mock_check:
        mock_check.return_value = {"tunnel": "OK", "stores": "OK", "mcp_server": "OK"}

        result = runner.invoke(app, ["agent", "status"])

        assert "tunnel: OK" in result.output
        assert "stores: OK" in result.output
        assert "mcp_server: OK" in result.output


def test_agent_status_prints_overall_ok_when_all_components_ok():
    with patch("dia.agent.runtime.check") as mock_check:
        mock_check.return_value = {"tunnel": "OK", "stores": "OK", "mcp_server": "OK"}

        result = runner.invoke(app, ["agent", "status"])

        assert result.output.strip().splitlines()[-1] == "OK"


def test_agent_status_prints_overall_failed_when_any_component_failed():
    with patch("dia.agent.runtime.check") as mock_check:
        mock_check.return_value = {"tunnel": "OK", "stores": "FAILED", "mcp_server": "SKIPPED"}

        result = runner.invoke(app, ["agent", "status"])

        assert result.output.strip().splitlines()[-1] == "FAILED"
