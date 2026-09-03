"""Tests for dia.agent.runtime.ask() — end-to-end orchestration (fully mocked).

Marked integration: this tests composition/ordering of multiple internal units
together (patches -> stores -> mcp server -> agent), not a single function in
isolation. Nothing here talks to real AWS/Neptune/OpenSearch/Bedrock — every
external call is patched.
"""

from unittest.mock import MagicMock, patch

import pytest

from dia.agent.models import AgentResponse
from dia.agent.runtime import ask

pytestmark = pytest.mark.integration


def _patch_all(**overrides):
    """Patch every external dependency of ask(), returning the patch objects."""
    patches = {
        "apply_all": patch("dia.agent.runtime.apply_all"),
        "build_graph_store": patch("dia.agent.runtime.stores.build_graph_store"),
        "build_vector_store": patch("dia.agent.runtime.stores.build_vector_store"),
        "build_graph_index": patch("dia.agent.runtime.stores.build_graph_index"),
        "build_mcp_server": patch("dia.agent.runtime.mcp_server.build_mcp_server"),
        "start_server": patch("dia.agent.runtime.mcp_server.start_server"),
        "make_default_agent": patch("dia.agent.runtime.agents.make_default_agent"),
        "settings": patch("dia.agent.runtime.settings"),
    }
    mocks = {name: p.start() for name, p in patches.items()}
    mocks["settings"].neptune_endpoint = "neptune-host"
    mocks["settings"].aoss_endpoint = "aoss-host"
    for name, value in overrides.items():
        mocks[name].side_effect = value
    return patches, mocks


def _stop_all(patches):
    for p in patches.values():
        p.stop()


def test_ask_calls_every_step_in_order():
    manager = MagicMock()
    patches, mocks = _patch_all()
    try:
        for name, mock in mocks.items():
            manager.attach_mock(mock, name)
        mocks["make_default_agent"].return_value = MagicMock(return_value="an answer")

        ask("Home Office", "what is the risk?")

        called_names = [c[0] for c in manager.mock_calls]
        assert called_names.index("apply_all") < called_names.index("build_graph_store")
        assert called_names.index("build_graph_store") < called_names.index("build_vector_store")
        assert called_names.index("build_vector_store") < called_names.index("build_graph_index")
        assert called_names.index("build_graph_index") < called_names.index("build_mcp_server")
        assert called_names.index("build_mcp_server") < called_names.index("start_server")
        assert called_names.index("start_server") < called_names.index("make_default_agent")
    finally:
        _stop_all(patches)


def test_ask_builds_vector_store_with_aoss_endpoint_not_neptune_endpoint():
    """Regression guard: an earlier bug passed settings.neptune_endpoint to
    build_vector_store() instead of settings.aoss_endpoint."""
    patches, mocks = _patch_all()
    try:
        mocks["make_default_agent"].return_value = MagicMock(return_value="an answer")

        ask("Home Office", "what is the risk?")

        mocks["build_graph_store"].assert_called_once_with("neptune-host")
        mocks["build_vector_store"].assert_called_once_with("aoss-host")
    finally:
        _stop_all(patches)


def test_ask_passes_query_to_the_agent():
    patches, mocks = _patch_all()
    try:
        fake_agent = MagicMock(return_value="an answer")
        mocks["make_default_agent"].return_value = fake_agent

        ask("Home Office", "what is the risk?")

        fake_agent.assert_called_once_with("what is the risk?")
    finally:
        _stop_all(patches)


def test_ask_passes_department_to_make_default_agent():
    patches, mocks = _patch_all()
    try:
        mocks["make_default_agent"].return_value = MagicMock(return_value="an answer")

        ask("Border Force", "what is the risk?")

        mocks["make_default_agent"].assert_called_once_with("Border Force")
    finally:
        _stop_all(patches)


def test_ask_returns_an_agent_response_wrapping_the_result():
    patches, mocks = _patch_all()
    try:
        mocks["make_default_agent"].return_value = MagicMock(return_value="an answer")

        result = ask("Home Office", "what is the risk?")

        assert isinstance(result, AgentResponse)
        assert result.department == "Home Office"
        assert result.query == "what is the risk?"
        assert result.output == "an answer"
    finally:
        _stop_all(patches)


@pytest.mark.parametrize(
    "failing_step",
    [
        "apply_all",
        "build_graph_store",
        "build_mcp_server",
        "make_default_agent",
    ],
)
def test_ask_propagates_exceptions_from_any_step(failing_step):
    patches, mocks = _patch_all()
    try:
        mocks["make_default_agent"].return_value = MagicMock(return_value="an answer")
        mocks[failing_step].side_effect = RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            ask("Home Office", "what is the risk?")
    finally:
        _stop_all(patches)
