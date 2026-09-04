import os
import signal
import socket
import subprocess
import time
from contextlib import contextmanager

from dia.agent.config import settings
from dia.cli_helpers import detect_environment
from dia.clients.neptune import register_tunnel_host


def _is_port_open(port: int, host: str) -> bool:
    """Check whether something is already listening on host:port."""
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


@contextmanager
def open_tunnel(
    phase: str | None = None,
    port: int = settings.neptune_port,
    timeout: float = settings.timeout,
    host: str = settings.host,
):
    """Ensure the Neptune SSH tunnel is open, reusing one if already running.

    Spawns scripts/neptune-tunnel.sh if needed, waits for it to become
    ready, then registers the tunnel host for Neptune calls. Only tears
    down the tunnel on exit if this call started it.
    """
    if phase is None:
        phase = detect_environment().short_name

    already_running = _is_port_open(port, host)
    proc = None

    try:
        if not already_running:
            proc = subprocess.Popen(
                ["scripts/neptune-tunnel.sh", phase],
                start_new_session=True,
            )
            start = time.monotonic()
            while not _is_port_open(port, host):
                if time.monotonic() - start > timeout:
                    raise TimeoutError("Neptune tunnel did not open in time")
                time.sleep(0.5)

        register_tunnel_host(settings.neptune_endpoint)
        yield
    finally:
        if proc is not None:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
