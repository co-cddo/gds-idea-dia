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


def test_agent_ask_passes_query_department_and_tunnel_through():
    with patch("dia.agent.runtime.ask") as mock_ask:
        mock_ask.return_value = "an answer"

        result = runner.invoke(
            app,
            ["agent", "ask", "--query", "what is the risk?", "--department", "Home Office", "--tunnel"],
        )

        assert result.exit_code == 0
        mock_ask.assert_called_once_with("Home Office", "what is the risk?", tunnel=True)


def test_agent_ask_defaults_department_none_and_tunnel_false():
    with patch("dia.agent.runtime.ask") as mock_ask:
        mock_ask.return_value = "an answer"

        result = runner.invoke(app, ["agent", "ask", "--query", "what is the risk?"])

        assert result.exit_code == 0
        mock_ask.assert_called_once_with(None, "what is the risk?", tunnel=False)


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


def test_agent_status_defaults_tunnel_true():
    with patch("dia.agent.runtime.check") as mock_check:
        mock_check.return_value = {"tunnel": "OK", "stores": "OK", "mcp_server": "OK"}

        runner.invoke(app, ["agent", "status"])

        mock_check.assert_called_once_with(tunnel=True)


def test_agent_status_has_no_way_to_disable_tunnel_from_the_cli():
    """Known gap: --tunnel has no --no-tunnel counterpart and already defaults to
    True, so there is currently no CLI-reachable way to pass tunnel=False into
    runtime.check() for `dia agent status` (unlike `ask`, where the default is
    False and --tunnel toggles it on)."""
    result = runner.invoke(app, ["agent", "status", "--help"])

    assert "--no-tunnel" not in result.output


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
