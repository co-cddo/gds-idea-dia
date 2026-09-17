"""MCP tool for recovering from Neptune graph-query timeouts (retry escalation)."""

import time


def wait_after_timeout(seconds: int = 30) -> str:
    """
    Wait for Neptune to recover after a TimeLimitExceededException or ReadTimeoutError.

    Call this immediately after ANY graph query (default_) returns a timeout error,
    before retrying with a throttled mode. Neptune needs time to clean up the
    terminated traversal — firing a retry immediately will also fail because Neptune
    is still occupied with housekeeping from the previous query.

    ESCALATION SEQUENCE — follow exactly:
    1. default_ times out → call wait_after_timeout(seconds=30) → retry with '_throttled'
    2. '_throttled' times out → call wait_after_timeout(seconds=30) → retry with '_super_throttled'
    '_super_throttled' is vector-only and cannot timeout.

    Args:
        seconds: How long to wait in seconds (default 30, max 60)
    """
    seconds = min(max(seconds, 5), 60)
    time.sleep(seconds)
    return f"Waited {seconds}s. Neptune should have recovered. Retry the query now with the next throttled mode."


def register(mcp_server) -> None:
    """Register the timeout-recovery tool onto an already-built MCP server."""
    mcp_server.tool()(wait_after_timeout)
