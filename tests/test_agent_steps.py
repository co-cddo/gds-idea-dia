"""Tests for dia.agent.steps — individual bootstrap steps (fully mocked).

Each step wraps a single external boundary (stores, MCP server, agent). These
tests check the exact calls/order/arguments each step makes, at the fine
granularity that used to live in test_agent_runtime.py before the steps were
split out of runtime.py.
"""

from unittest.mock import MagicMock, patch

from dia.agent.steps import _connect_stores, _run_agent, _start_mcp_server

# ---------------------------------------------------------------------------
# _connect_stores
# ---------------------------------------------------------------------------


def test_connect_stores_builds_graph_store_with_neptune_endpoint():
    with (
        patch("dia.agent.steps.stores.build_graph_store") as build_graph_store,
        patch("dia.agent.steps.stores.build_vector_store"),
        patch("dia.agent.steps.stores.build_graph_index"),
        patch("dia.agent.steps.settings") as settings,
    ):
        settings.neptune_endpoint = "neptune-host"
        settings.aoss_endpoint = "aoss-host"

        _connect_stores()

        build_graph_store.assert_called_once_with("neptune-host")


def test_connect_stores_builds_vector_store_with_aoss_endpoint_not_neptune_endpoint():
    """Regression guard: an earlier bug passed settings.neptune_endpoint to
    build_vector_store() instead of settings.aoss_endpoint."""
    with (
        patch("dia.agent.steps.stores.build_graph_store"),
        patch("dia.agent.steps.stores.build_vector_store") as build_vector_store,
        patch("dia.agent.steps.stores.build_graph_index"),
        patch("dia.agent.steps.settings") as settings,
    ):
        settings.neptune_endpoint = "neptune-host"
        settings.aoss_endpoint = "aoss-host"

        _connect_stores()

        build_vector_store.assert_called_once_with("aoss-host")


def test_connect_stores_calls_steps_in_order_and_warms_up_index():
    manager = MagicMock()
    with (
        patch("dia.agent.steps.stores.build_graph_store") as build_graph_store,
        patch("dia.agent.steps.stores.build_vector_store") as build_vector_store,
        patch("dia.agent.steps.stores.build_graph_index") as build_graph_index,
        patch("dia.agent.steps.settings") as settings,
    ):
        settings.neptune_endpoint = "neptune-host"
        settings.aoss_endpoint = "aoss-host"
        build_graph_store.return_value = "graph_store"
        build_vector_store.return_value = "vector_store"
        manager.attach_mock(build_graph_store, "build_graph_store")
        manager.attach_mock(build_vector_store, "build_vector_store")
        manager.attach_mock(build_graph_index, "build_graph_index")

        _connect_stores()

        called_names = [c[0] for c in manager.mock_calls]
        assert called_names.index("build_graph_store") < called_names.index("build_vector_store")
        assert called_names.index("build_vector_store") < called_names.index("build_graph_index")
        build_graph_index.assert_called_once_with("graph_store", "vector_store")


def test_connect_stores_returns_graph_store_and_vector_store():
    with (
        patch("dia.agent.steps.stores.build_graph_store") as build_graph_store,
        patch("dia.agent.steps.stores.build_vector_store") as build_vector_store,
        patch("dia.agent.steps.stores.build_graph_index"),
        patch("dia.agent.steps.settings"),
    ):
        build_graph_store.return_value = "graph_store"
        build_vector_store.return_value = "vector_store"

        graph_store, vector_store = _connect_stores()

        assert graph_store == "graph_store"
        assert vector_store == "vector_store"


# ---------------------------------------------------------------------------
# _start_mcp_server
# ---------------------------------------------------------------------------


def test_start_mcp_server_builds_then_starts_server():
    manager = MagicMock()
    with (
        patch("dia.agent.steps.mcp_server.build_mcp_server") as build_mcp_server,
        patch("dia.agent.steps.mcp_server.start_server") as start_server,
    ):
        build_mcp_server.return_value = "server"
        start_server.return_value = "http://127.0.0.1:8000/mcp/"
        manager.attach_mock(build_mcp_server, "build_mcp_server")
        manager.attach_mock(start_server, "start_server")

        result = _start_mcp_server("graph_store", "vector_store")

        build_mcp_server.assert_called_once_with("graph_store", "vector_store")
        start_server.assert_called_once_with("server")
        called_names = [c[0] for c in manager.mock_calls]
        assert called_names.index("build_mcp_server") < called_names.index("start_server")
        assert result == "http://127.0.0.1:8000/mcp/"


# ---------------------------------------------------------------------------
# _run_agent
# ---------------------------------------------------------------------------


def test_run_agent_builds_agent_scoped_to_department():
    with patch("dia.agent.steps.agents.make_default_agent") as make_default_agent:
        make_default_agent.return_value = MagicMock(return_value="an answer")

        _run_agent("Home Office", "what is the risk?")

        make_default_agent.assert_called_once_with("Home Office")


def test_run_agent_passes_query_to_the_agent():
    with patch("dia.agent.steps.agents.make_default_agent") as make_default_agent:
        fake_agent = MagicMock(return_value="an answer")
        make_default_agent.return_value = fake_agent

        _run_agent("Home Office", "what is the risk?")

        fake_agent.assert_called_once_with("what is the risk?")


def test_run_agent_returns_result_as_str():
    with patch("dia.agent.steps.agents.make_default_agent") as make_default_agent:
        make_default_agent.return_value = MagicMock(return_value=12345)

        result = _run_agent("Home Office", "what is the risk?")

        assert result == "12345"
        assert isinstance(result, str)
