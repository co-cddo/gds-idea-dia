"""MCP server construction and lifecycle (start/stop/verify)."""

import subprocess
import threading
import time
from typing import Any

from graphrag_toolkit.lexical_graph.protocols import create_mcp_server
from mcp.client.streamable_http import streamable_http_client
from strands.tools.mcp.mcp_client import MCPClient

from .retrieval_modes import _DEFAULT_TOOL_DESCRIPTION, tool_parameters

DEFAULT_MCP_PORT = 8000


def build_mcp_server(graph_store, vector_store):
    """Build the MCP server, registering the default_ retrieval tool.

    graph_store/vector_store must already be connected (see stores.py) —
    build_graph_index() must have run first, or tool registration fails.
    """
    tenant_cfg = {
        "default_": {
            "description": _DEFAULT_TOOL_DESCRIPTION,
            "tool_parameters": tool_parameters,
            "query_engine_args": {"enable_multipart_queries": False},
        }
    }
    return create_mcp_server(graph_store, vector_store, tenant_ids=tenant_cfg)


_server_state: dict[str, Any] = {"thread": None, "url": None}


def _kill_existing_on_port(port: int) -> None:
    """Best-effort: kill any process listening on `port`."""
    try:
        result = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True)
        if result.stdout.strip():
            for pid in result.stdout.strip().split("\n"):
                subprocess.run(["kill", "-9", pid], capture_output=True)
            time.sleep(1)
            print(f"Killed previous process on port {port}")
    except Exception:
        pass


def start_server(
    mcp_server,
    port: int = DEFAULT_MCP_PORT,
    *,
    log_level: str = "warning",
    verify: bool = True,
    kill_existing: bool = True,
) -> str:
    """Start the MCP server on a background daemon thread.

    Args:
        mcp_server: the server object returned by build_mcp_server().
        port: TCP port to bind to (default 8000).
        log_level: graphrag-toolkit log level for the server.
        verify: If True, connect a short-lived MCP client and print the registered tools.
        kill_existing: If True, kill any process already on the port before starting.

    Returns:
        The MCP HTTP URL (e.g. "http://127.0.0.1:8000/mcp/").

    Calling this twice is a no-op (the existing server URL is returned).
    """
    if _server_state["thread"] is not None and _server_state["thread"].is_alive():
        print(f"MCP server already running at {_server_state['url']}")
        return _server_state["url"]

    if kill_existing:
        _kill_existing_on_port(port)

    url = f"http://127.0.0.1:{port}/mcp/"

    def _run() -> None:
        mcp_server.run(transport="streamable-http", log_level=log_level)

    thread = threading.Thread(target=_run, daemon=True, name="mcp-server")
    thread.start()
    _server_state["thread"] = thread
    _server_state["url"] = url

    time.sleep(3)
    print(f"MCP Server started on {url}")

    if verify:
        try:
            verify_client = MCPClient(lambda: streamable_http_client(url))
            with verify_client:
                tools = verify_client.list_tools_sync()
                print(f"Registered {len(tools)} tools:")
                for tool in tools:
                    print(f"  - {tool.tool_spec['name']}")
        except Exception as e:
            print(f"Tool verification failed: {e}")

    return url


def server_url() -> str:
    """Return the URL of the running MCP server.

    Raises RuntimeError if the server hasn't been started yet.
    """
    if _server_state["url"] is None:
        raise RuntimeError("MCP server has not been started. Call start_server() first.")
    return _server_state["url"]
