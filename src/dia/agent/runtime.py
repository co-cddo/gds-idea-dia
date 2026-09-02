"""End-to-end agent bootstrap: config -> stores -> MCP server -> agent -> answer."""

import logging

from dia.agent import agents, stores
from dia.agent.config import settings
from dia.agent.mcp import server as mcp_server
from dia.agent.model import AgentResponse
from dia.agent.patches import apply_all

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def ask(department: str, query: str) -> AgentResponse:
    try:
        apply_all()
        logger.info("[1/5] Toolkit bugfix patches applied")
    except Exception as e:
        logger.error("failed applying patches: %s", e)
        raise

    try:
        graph_store = stores.build_graph_store(settings.neptune_endpoint)
        vector_store = stores.build_vector_store(settings.aoss_endpoint)
        stores.build_graph_index(graph_store, vector_store)
        logger.info("[2/5] Connected to stores")
    except Exception as e:
        logger.error("failed connecting to stores: %s", e)
        raise

    try:
        server = mcp_server.build_mcp_server(graph_store, vector_store)
        mcp_server.start_server(server)
        logger.info("[3/5] Started MCP server")
    except Exception as e:
        logger.error("failed starting MCP server: %s", e)
        raise

    try:
        agent = agents.make_default_agent(department)
        logger.info("[4/5] Call dia agent")
        result = agent(query)
    except Exception as e:
        logger.error("failed calling agent: %s", e)
        raise

    try:
        response = AgentResponse(department=department, query=query, output=str(result))
        logger.info("[5/5] Finito!")
    except Exception as e:
        logger.error("failed building response object: %s", e)
        raise

    return response
