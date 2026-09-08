from dia.agent import agents, stores
from dia.agent.config import settings
from dia.agent.mcp import server as mcp_server


def _connect_stores():
    """Connect to Neptune/AOSS and warm up the graph index. Must run before _start_mcp_server()."""
    graph_store = stores.build_graph_store(settings.neptune_endpoint)
    vector_store = stores.build_vector_store(settings.aoss_endpoint)
    stores.build_graph_index(graph_store, vector_store)
    return graph_store, vector_store


def _start_mcp_server(graph_store, vector_store):
    """Build and start the MCP server; graph_store/vector_store must already be connected. Returns the server URL."""
    server = mcp_server.build_mcp_server(graph_store, vector_store)
    return mcp_server.start_server(server)


def _run_agent(department, query) -> str:
    """Build the default agent scoped to department and run query, returning the answer as str."""
    agent = agents.make_default_agent(department)
    result = agent(query)
    return str(result)
