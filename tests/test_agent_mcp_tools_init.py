"""Tests for dia.agent.mcp.tools.register_all_tools — wires up all tool modules."""

from unittest.mock import MagicMock, patch

from dia.agent.mcp.tools import register_all_tools


@patch("dia.agent.mcp.tools.web_search.register")
@patch("dia.agent.mcp.tools.knowledge_base.register")
@patch("dia.agent.mcp.tools.graph.register")
@patch("dia.agent.mcp.tools.athena.register")
def test_register_all_tools_registers_athena(mock_athena, mock_graph, mock_kb, mock_web):
    mock_server = MagicMock()
    register_all_tools(mock_server)

    mock_athena.assert_called_once_with(mock_server)


@patch("dia.agent.mcp.tools.web_search.register")
@patch("dia.agent.mcp.tools.knowledge_base.register")
@patch("dia.agent.mcp.tools.graph.register")
@patch("dia.agent.mcp.tools.athena.register")
def test_register_all_tools_registers_graph(mock_athena, mock_graph, mock_kb, mock_web):
    mock_server = MagicMock()
    register_all_tools(mock_server)

    mock_graph.assert_called_once_with(mock_server)


@patch("dia.agent.mcp.tools.web_search.register")
@patch("dia.agent.mcp.tools.knowledge_base.register")
@patch("dia.agent.mcp.tools.graph.register")
@patch("dia.agent.mcp.tools.athena.register")
def test_register_all_tools_registers_knowledge_base(mock_athena, mock_graph, mock_kb, mock_web):
    mock_server = MagicMock()
    register_all_tools(mock_server)

    mock_kb.assert_called_once_with(mock_server)


@patch("dia.agent.mcp.tools.web_search.register")
@patch("dia.agent.mcp.tools.knowledge_base.register")
@patch("dia.agent.mcp.tools.graph.register")
@patch("dia.agent.mcp.tools.athena.register")
def test_register_all_tools_registers_web_search(mock_athena, mock_graph, mock_kb, mock_web):
    mock_server = MagicMock()
    register_all_tools(mock_server)

    mock_web.assert_called_once_with(mock_server)
