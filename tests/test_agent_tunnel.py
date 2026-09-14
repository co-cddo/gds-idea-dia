"""Tests for dia.agent.tunnel — ensure_tunnel_open()'s readiness-poll/reuse/timeout/
teardown logic.

Every external dependency (subprocess.Popen, socket-connect via
_is_port_open, os.getpgid/killpg, time.sleep/monotonic, register_tunnel_host,
detect_environment, and the secret-backed settings.neptune_endpoint) is
mocked, so no real AWS/SSH/subprocess/socket calls happen.
"""

import signal
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from dia.agent.config import Settings
from dia.agent.tunnel import ensure_tunnel_open


def _patch_all(**overrides):
    """Patch every external dependency of ensure_tunnel_open(), returning (patches, mocks)."""
    patches = {
        "Popen": patch("dia.agent.tunnel.subprocess.Popen"),
        "_is_port_open": patch("dia.agent.tunnel._is_port_open"),
        "sleep": patch("dia.agent.tunnel.time.sleep"),
        "monotonic": patch("dia.agent.tunnel.time.monotonic"),
        "getpgid": patch("dia.agent.tunnel.os.getpgid"),
        "killpg": patch("dia.agent.tunnel.os.killpg"),
        "register_tunnel_host": patch("dia.agent.tunnel.register_tunnel_host"),
        "detect_environment": patch("dia.agent.tunnel.detect_environment"),
        "neptune_endpoint": patch.object(Settings, "neptune_endpoint", new_callable=PropertyMock),
    }
    mocks = {name: p.start() for name, p in patches.items()}

    mocks["Popen"].return_value = MagicMock(pid=12345)
    mocks["getpgid"].return_value = 999
    mocks["monotonic"].return_value = 0.0
    mocks["neptune_endpoint"].return_value = "neptune-tunnel-host.example.com"
    mocks["detect_environment"].return_value = MagicMock(short_name="dev")

    for name, value in overrides.items():
        mocks[name].side_effect = value
    return patches, mocks


def _stop_all(patches):
    for p in patches.values():
        p.stop()


# ---------------------------------------------------------------------------
# reuse-when-port-open
# ---------------------------------------------------------------------------


def test_reuses_existing_tunnel_without_spawning_subprocess():
    patches, mocks = _patch_all(_is_port_open=[True])
    try:
        with ensure_tunnel_open(phase="dev", port=8182, timeout=30.0, host="127.0.0.1"):
            pass

        mocks["Popen"].assert_not_called()
    finally:
        _stop_all(patches)


def test_registers_tunnel_host_with_configured_endpoint_when_reused():
    patches, mocks = _patch_all(_is_port_open=[True])
    try:
        with ensure_tunnel_open(phase="dev", port=8182, timeout=30.0, host="127.0.0.1"):
            pass

        mocks["register_tunnel_host"].assert_called_once_with("neptune-tunnel-host.example.com")
    finally:
        _stop_all(patches)


def test_does_not_kill_process_when_tunnel_was_already_running():
    patches, mocks = _patch_all(_is_port_open=[True])
    try:
        with ensure_tunnel_open(phase="dev", port=8182, timeout=30.0, host="127.0.0.1"):
            pass

        mocks["killpg"].assert_not_called()
    finally:
        _stop_all(patches)


# ---------------------------------------------------------------------------
# spawn-when-not
# ---------------------------------------------------------------------------


def test_spawns_subprocess_when_port_not_already_open():
    patches, mocks = _patch_all(_is_port_open=[False, True])
    try:
        with ensure_tunnel_open(phase="dev", port=8182, timeout=30.0, host="127.0.0.1"):
            pass

        mocks["Popen"].assert_called_once_with(["scripts/neptune-tunnel.sh", "dev"], start_new_session=True)
    finally:
        _stop_all(patches)


def test_registers_tunnel_host_after_spawning():
    patches, mocks = _patch_all(_is_port_open=[False, True])
    try:
        with ensure_tunnel_open(phase="dev", port=8182, timeout=30.0, host="127.0.0.1"):
            pass

        mocks["register_tunnel_host"].assert_called_once_with("neptune-tunnel-host.example.com")
    finally:
        _stop_all(patches)


def test_kills_process_group_on_exit_when_we_started_it():
    patches, mocks = _patch_all(_is_port_open=[False, True])
    try:
        with ensure_tunnel_open(phase="dev", port=8182, timeout=30.0, host="127.0.0.1"):
            pass

        mocks["getpgid"].assert_called_once_with(12345)
        mocks["killpg"].assert_called_once_with(999, signal.SIGTERM)
    finally:
        _stop_all(patches)


def test_default_phase_uses_detect_environment_short_name():
    patches, mocks = _patch_all(_is_port_open=[False, True])
    try:
        with ensure_tunnel_open(port=8182, timeout=30.0, host="127.0.0.1"):
            pass

        mocks["Popen"].assert_called_once_with(["scripts/neptune-tunnel.sh", "dev"], start_new_session=True)
    finally:
        _stop_all(patches)


# ---------------------------------------------------------------------------
# timeout -> TimeoutError
# ---------------------------------------------------------------------------


def test_raises_timeout_error_when_port_never_opens():
    patches, mocks = _patch_all(
        _is_port_open=[False] * 10,
        monotonic=[0.0, 100.0],
    )
    try:
        with pytest.raises(TimeoutError, match="Neptune tunnel did not open in time"):
            with ensure_tunnel_open(phase="dev", port=8182, timeout=30.0, host="127.0.0.1"):
                pass
    finally:
        _stop_all(patches)


def test_kills_process_group_even_on_timeout():
    """Regression guard: teardown is keyed on 'did we start the subprocess',
    not on 'did we succeed'. The subprocess was already spawned before the
    poll loop timed out, so it must still be torn down in `finally`."""
    patches, mocks = _patch_all(
        _is_port_open=[False] * 10,
        monotonic=[0.0, 100.0],
    )
    try:
        with pytest.raises(TimeoutError):
            with ensure_tunnel_open(phase="dev", port=8182, timeout=30.0, host="127.0.0.1"):
                pass

        mocks["getpgid"].assert_called_once_with(12345)
        mocks["killpg"].assert_called_once_with(999, signal.SIGTERM)
    finally:
        _stop_all(patches)


def test_does_not_register_tunnel_host_on_timeout():
    patches, mocks = _patch_all(
        _is_port_open=[False] * 10,
        monotonic=[0.0, 100.0],
    )
    try:
        with pytest.raises(TimeoutError):
            with ensure_tunnel_open(phase="dev", port=8182, timeout=30.0, host="127.0.0.1"):
                pass

        mocks["register_tunnel_host"].assert_not_called()
    finally:
        _stop_all(patches)
