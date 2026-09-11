"""End-to-end agent bootstrap: config -> stores -> MCP server -> agent -> answer."""

import logging
from contextlib import ExitStack, nullcontext

from dia.agent.models import AgentInput, AgentResponse, CheckStatus
from dia.agent.patches import apply_all
from dia.agent.steps import _connect_stores, _run_agent, _start_mcp_server
from dia.agent.tunnel import open_tunnel

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def check(*, tunnel: bool = True) -> dict[str, CheckStatus]:
    """Connectivity check: tunnel -> stores -> mcp_server, skipping later steps on failure. No LLM call."""
    result: dict[str, CheckStatus] = {
        "tunnel": CheckStatus.SKIPPED,
        "stores": CheckStatus.SKIPPED,
        "mcp_server": CheckStatus.SKIPPED,
    }

    with ExitStack() as stack:
        if tunnel:
            try:
                stack.enter_context(open_tunnel())
                result["tunnel"] = CheckStatus.OK
            except Exception as e:
                logger.error("tunnel check failed: %s", e)
                result["tunnel"] = CheckStatus.FAILED
                return result

        try:
            graph_store, vector_store = _connect_stores()
            result["stores"] = CheckStatus.OK
        except Exception as e:
            logger.error("stores check failed: %s", e)
            result["stores"] = CheckStatus.FAILED
            return result

        try:
            _start_mcp_server(graph_store, vector_store)
            result["mcp_server"] = CheckStatus.OK
        except Exception as e:
            logger.error("mcp_server check failed: %s", e)
            result["mcp_server"] = CheckStatus.FAILED

    return result


def ask(department: str | None, query: str, *, tunnel: bool = False) -> AgentResponse:
    """Run the agent end-to-end for a scoped query.

    Applies patches, connects to Neptune/AOSS, starts the MCP server,
    and calls the default agent. Auto-opens the Neptune
    SSH tunnel for the duration of the call.
    """
    agent_input = AgentInput(department=department, query=query)
    ctx = open_tunnel() if tunnel else nullcontext()
    with ctx:
        try:
            apply_all()
            logger.info("[1/5] Toolkit bugfix patches applied")
        except Exception as e:
            logger.error("failed applying patches: %s", e)
            raise
        try:
            graph_store, vector_store = _connect_stores()
            logger.info("[2/5] Connected to stores")
        except Exception as e:
            logger.error("failed connecting to stores: %s", e)
            raise

        try:
            _start_mcp_server(graph_store, vector_store)
            logger.info("[3/5] Started MCP server")
        except Exception as e:
            logger.error("failed starting MCP server: %s", e)
            raise

        try:
            output = _run_agent(agent_input.department, agent_input.query)
            logger.info("[4/5] Call dia agent")
        except Exception as e:
            logger.error("failed calling agent: %s", e)
            raise

        try:
            response = AgentResponse(department=agent_input.department, query=agent_input.query, output=str(output))
            logger.info("[5/5] Finito!")
        except Exception as e:
            logger.error("failed building response object: %s", e)
            raise
        print(response)
        return response
