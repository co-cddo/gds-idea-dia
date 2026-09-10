"""Tests for dia.agent.runtime — end-to-end orchestration (fully mocked).

Marked integration: this tests composition/ordering of multiple internal units
together (patches -> steps -> agent, or tunnel -> steps for check()), not a
single function in isolation. Nothing here talks to real AWS/Neptune/
OpenSearch/Bedrock/SSH — every external call is patched. Fine-grained
argument/order assertions for each individual step (e.g. build_vector_store
called with the aoss endpoint, not neptune) live in test_agent_steps.py.
"""

from unittest.mock import MagicMock, patch

import pytest

from dia.agent.models import AgentResponse
from dia.agent.runtime import ask, check

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# ask()
# ---------------------------------------------------------------------------


def _patch_all(**overrides):
    """Patch every external dependency of ask(), returning the patch objects."""
    patches = {
        "apply_all": patch("dia.agent.runtime.apply_all"),
        "_connect_stores": patch("dia.agent.runtime._connect_stores"),
        "_start_mcp_server": patch("dia.agent.runtime._start_mcp_server"),
        "_run_agent": patch("dia.agent.runtime._run_agent"),
    }
    mocks = {name: p.start() for name, p in patches.items()}
    mocks["_connect_stores"].return_value = ("graph_store", "vector_store")
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
        mocks["_run_agent"].return_value = "an answer"

        ask("Home Office", "what is the risk?")

        called_names = [c[0] for c in manager.mock_calls]
        assert called_names.index("apply_all") < called_names.index("_connect_stores")
        assert called_names.index("_connect_stores") < called_names.index("_start_mcp_server")
        assert called_names.index("_start_mcp_server") < called_names.index("_run_agent")
    finally:
        _stop_all(patches)


def test_ask_passes_stores_from_connect_stores_into_start_mcp_server():
    patches, mocks = _patch_all()
    try:
        mocks["_run_agent"].return_value = "an answer"

        ask("Home Office", "what is the risk?")

        mocks["_start_mcp_server"].assert_called_once_with("graph_store", "vector_store")
    finally:
        _stop_all(patches)


def test_ask_passes_query_to_run_agent():
    patches, mocks = _patch_all()
    try:
        mocks["_run_agent"].return_value = "an answer"

        ask("Home Office", "what is the risk?")

        mocks["_run_agent"].assert_called_once_with("Home Office", "what is the risk?")
    finally:
        _stop_all(patches)


def test_ask_passes_department_to_run_agent():
    patches, mocks = _patch_all()
    try:
        mocks["_run_agent"].return_value = "an answer"

        ask("Border Force", "what is the risk?")

        mocks["_run_agent"].assert_called_once_with("Border Force", "what is the risk?")
    finally:
        _stop_all(patches)


def test_ask_returns_an_agent_response_wrapping_the_result():
    patches, mocks = _patch_all()
    try:
        mocks["_run_agent"].return_value = "an answer"

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
        "_connect_stores",
        "_start_mcp_server",
        "_run_agent",
    ],
)
def test_ask_propagates_exceptions_from_any_step(failing_step):
    patches, mocks = _patch_all()
    try:
        mocks["_run_agent"].return_value = "an answer"
        mocks[failing_step].side_effect = RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            ask("Home Office", "what is the risk?")
    finally:
        _stop_all(patches)


# ---------------------------------------------------------------------------
# check()
# ---------------------------------------------------------------------------


def _patch_check(**overrides):
    """Patch every external dependency of check(), returning the patch objects."""
    patches = {
        "_is_port_open": patch("dia.agent.runtime._is_port_open"),
        "register_tunnel_host": patch("dia.agent.runtime.register_tunnel_host"),
        "_connect_stores": patch("dia.agent.runtime._connect_stores"),
        "_start_mcp_server": patch("dia.agent.runtime._start_mcp_server"),
        "_run_agent": patch("dia.agent.runtime._run_agent"),
    }
    mocks = {name: p.start() for name, p in patches.items()}
    mocks["_is_port_open"].return_value = True
    mocks["_connect_stores"].return_value = ("graph_store", "vector_store")
    for name, value in overrides.items():
        mocks[name].side_effect = value
    return patches, mocks


def test_check_happy_path_all_ok():
    patches, mocks = _patch_check()
    try:
        result = check(tunnel=True)

        mocks["register_tunnel_host"].assert_called_once()
        assert result == {"tunnel": "OK", "stores": "OK", "mcp_server": "OK"}
    finally:
        _stop_all(patches)


def test_check_tunnel_skipped_when_tunnel_false_but_stores_and_mcp_server_still_attempted():
    patches, mocks = _patch_check()
    try:
        result = check(tunnel=False)

        mocks["_is_port_open"].assert_not_called()
        mocks["_connect_stores"].assert_called_once()
        mocks["_start_mcp_server"].assert_called_once()
        assert result == {"tunnel": "SKIPPED", "stores": "OK", "mcp_server": "OK"}
    finally:
        _stop_all(patches)


def test_check_stores_and_mcp_server_skipped_when_tunnel_fails():
    """check()'s tunnel check is a read-only peek at the port - it should never
    spawn/tear down a tunnel process. When nothing is listening, stores/mcp_server
    must be skipped and register_tunnel_host() must not run."""
    patches, mocks = _patch_check()
    try:
        mocks["_is_port_open"].return_value = False

        result = check(tunnel=True)

        mocks["register_tunnel_host"].assert_not_called()
        mocks["_connect_stores"].assert_not_called()
        mocks["_start_mcp_server"].assert_not_called()
        assert result == {"tunnel": "FAILED", "stores": "SKIPPED", "mcp_server": "SKIPPED"}
    finally:
        _stop_all(patches)


def test_check_mcp_server_skipped_when_stores_fails():
    patches, mocks = _patch_check(_connect_stores=RuntimeError("boom"))
    try:
        result = check(tunnel=True)

        mocks["_start_mcp_server"].assert_not_called()
        assert result == {"tunnel": "OK", "stores": "FAILED", "mcp_server": "SKIPPED"}
    finally:
        _stop_all(patches)


def test_check_mcp_server_failure_is_reported_not_raised():
    patches, mocks = _patch_check(_start_mcp_server=RuntimeError("boom"))
    try:
        result = check(tunnel=True)

        assert result == {"tunnel": "OK", "stores": "OK", "mcp_server": "FAILED"}
    finally:
        _stop_all(patches)


@pytest.mark.parametrize("tunnel", [True, False])
def test_check_never_calls_run_agent(tunnel):
    patches, mocks = _patch_check()
    try:
        check(tunnel=tunnel)

        mocks["_run_agent"].assert_not_called()
    finally:
        _stop_all(patches)
