"""Tests for dia.agent.mcp.server.build_mcp_server — server construction + tool registration."""

from unittest.mock import MagicMock, patch

from dia.agent.mcp.server import build_mcp_server


def test_build_mcp_server_registers_tools_on_created_server():
    fake_server = MagicMock()
    with (
        patch("dia.agent.mcp.server.create_mcp_server", return_value=fake_server),
        patch("dia.agent.mcp.server.register_all_tools") as mock_register_all_tools,
    ):
        build_mcp_server(graph_store=object(), vector_store=object())

        mock_register_all_tools.assert_called_once_with(fake_server)


def test_build_mcp_server_returns_the_created_server():
    fake_server = MagicMock()
    with (
        patch("dia.agent.mcp.server.create_mcp_server", return_value=fake_server),
        patch("dia.agent.mcp.server.register_all_tools"),
    ):
        result = build_mcp_server(graph_store=object(), vector_store=object())

        assert result is fake_server


def test_build_mcp_server_passes_stores_to_create_mcp_server():
    graph_store = object()
    vector_store = object()
    with (
        patch("dia.agent.mcp.server.create_mcp_server", return_value=MagicMock()) as mock_create,
        patch("dia.agent.mcp.server.register_all_tools"),
    ):
        build_mcp_server(graph_store, vector_store)

        args, _ = mock_create.call_args
        assert args[0] is graph_store
        assert args[1] is vector_store
