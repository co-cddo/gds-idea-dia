"""Graph/vector store construction: build_graph_store(), build_vector_store(), build_graph_index()."""

from graphrag_toolkit.lexical_graph import LexicalGraphIndex  # noqa: E402
from graphrag_toolkit.lexical_graph.storage import (  # noqa: E402
    GraphStoreFactory,
    VectorStoreFactory,
)


def build_graph_store(endpoint: str):
    """Connect to the Neptune graph database at the given endpoint."""
    return GraphStoreFactory.for_graph_store(endpoint)


def build_vector_store(endpoint: str):
    """Connect to the OpenSearch (AOSS) vector store at the given endpoint."""
    return VectorStoreFactory.for_vector_store(endpoint)


def build_graph_index(graph_store, vector_store):
    """Warm up graph store connection and cache graph summary.

    Required for create_mcp_server() to register the default_ tool
    successfully — must be called before building the MCP server.
    """
    return LexicalGraphIndex(graph_store, vector_store)
