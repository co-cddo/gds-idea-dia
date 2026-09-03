"""MCP tool implementations: Athena, Bedrock Knowledge Base, and web search."""

from dia.agent.mcp.tools import athena, graph, knowledge_base, web_search


def register_all_tools(mcp_server) -> None:
    """Register the Athena, graph-timeout, knowledge-base, and web-search tool modules."""
    athena.register(mcp_server)
    graph.register(mcp_server)
    knowledge_base.register(mcp_server)
    web_search.register(mcp_server)
