"""Tests for dia.agent.mcp.tools.graph — Neptune timeout-recovery MCP tool."""

from unittest.mock import MagicMock, patch

from dia.agent.mcp.tools import graph


@patch("dia.agent.mcp.tools.graph.time.sleep")
def test_wait_after_timeout_default_seconds(mock_sleep):
    result = graph.wait_after_timeout()

    mock_sleep.assert_called_once_with(30)
    assert "30s" in result


@patch("dia.agent.mcp.tools.graph.time.sleep")
def test_wait_after_timeout_clamps_below_minimum(mock_sleep):
    graph.wait_after_timeout(seconds=1)

    mock_sleep.assert_called_once_with(5)


@patch("dia.agent.mcp.tools.graph.time.sleep")
def test_wait_after_timeout_clamps_above_maximum(mock_sleep):
    graph.wait_after_timeout(seconds=999)

    mock_sleep.assert_called_once_with(60)


@patch("dia.agent.mcp.tools.graph.time.sleep")
def test_wait_after_timeout_passes_through_value_within_range(mock_sleep):
    graph.wait_after_timeout(seconds=45)

    mock_sleep.assert_called_once_with(45)


@patch("dia.agent.mcp.tools.graph.time.sleep")
def test_wait_after_timeout_message_reflects_clamped_value(mock_sleep):
    result = graph.wait_after_timeout(seconds=999)

    assert "60s" in result
    assert "Retry the query now" in result


def test_register_attaches_wait_after_timeout_to_server():
    mock_server = MagicMock()
    mock_tool_decorator = MagicMock()
    mock_server.tool.return_value = mock_tool_decorator

    graph.register(mock_server)

    mock_server.tool.assert_called_once()
    mock_tool_decorator.assert_called_once_with(graph.wait_after_timeout)
