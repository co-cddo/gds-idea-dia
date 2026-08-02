# Testing the agent end-to-end, without Neptune

Neptune connectivity is a separate workstream (owned elsewhere). This doc
covers building and testing every other agent tool — Athena, Bedrock KB,
Tavily web search, and OpenSearch (AOSS) — end-to-end through a real Strands
agent, without needing Neptune to be reachable at all.

Why this is safe: `build_mcp_server()` (the function that wires in Neptune)
runs real Cypher queries against Neptune during setup (to auto-generate the
`default_` tool's description). If Neptune is unreachable, that call raises
an uncaught exception and crashes the whole server-build step — which would
block every other tool too, not just the graph one. This plan avoids that
entirely by never calling `build_mcp_server()`/`create_mcp_server()` — it
builds a bare MCP server instead and registers only the Neptune-independent
tools onto it.

## 2. New tool: `mcp/tools/opensearch.py`

A new file, following the same shape as `athena.py`/`knowledge_base.py`:

```python
from opensearchpy import OpenSearch, AWSV4SignerAuth, RequestsHttpConnection

from dia.agent.config import settings
from dia.clients.session import get_session


def _opensearch_client() -> OpenSearch:
    session = get_session()
    auth = AWSV4SignerAuth(session.get_credentials(), settings.aws_region, "aoss")
    return OpenSearch(
        hosts=[{"host": settings.aoss_endpoint, "port": 443}],
        http_auth=auth,
        use_ssl=True,
        connection_class=RequestsHttpConnection,
    )


def search_opensearch(query: str, top_k: int = 10) -> str:
    """Full-text search over the chunk/statement indexes in OpenSearch."""
    client = _opensearch_client()
    response = client.search(
        index="chunk",
        body={"query": {"match": {"value": query}}, "size": top_k},
    )
    # format response["hits"]["hits"] into a JSON string, same shape as
    # kb_search_* results (text/score/source per hit)
    ...


def register(mcp_server) -> None:
    mcp_server.tool()(search_opensearch)
```

Prerequisite: `settings.aoss_endpoint` property added to `config.py` (via the
shared `_resolve_secret()` helper), and the `dia-aoss-endpoint-{phase}` secret
populated with the real collection endpoint.

## 3. Add missing `register()` functions

Confirmed gaps (checked via grep — only `athena.py` currently has one):

- `mcp/tools/knowledge_base.py` — add:

  ```python
  def register(mcp_server) -> None:
      mcp_server.tool()(kb_search_gats_business_cases)
      mcp_server.tool()(kb_search_sr25_bids)
      mcp_server.tool()(kb_search_sr21_bids)
      mcp_server.tool()(kb_search_nao_reports)
      mcp_server.tool()(kb_search_efficiency_reports)
  ```

- `mcp/tools/web_search.py` — add:

  ```python
  def register(mcp_server) -> None:
      mcp_server.tool()(web_search_gov)
  ```

- `mcp/tools/graph.py` — add:

  ```python
  def register(mcp_server) -> None:
      mcp_server.tool()(wait_after_timeout)
  ```

- `mcp/tools/athena.py` — already has `register()`, no change needed.

## 4. Bootstrap/test script

A new script (proposed: `scripts/test_agent_without_neptune.py`) that builds
a bare MCP server (skipping `build_mcp_server()`/Neptune entirely),
registers every Neptune-independent tool onto it, starts it, and builds a
real agent against it:

```python
from fastmcp import FastMCP

from dia.agent.mcp.server import start_server
from dia.agent.mcp.tools import athena, knowledge_base, web_search, graph, opensearch
from dia.agent.agents import make_default_agent

mcp_server = FastMCP(name="LexicalGraphServer")

athena.register(mcp_server)
knowledge_base.register(mcp_server)
web_search.register(mcp_server)
graph.register(mcp_server)
opensearch.register(mcp_server)

start_server(mcp_server)

agent = make_default_agent("Home Office")
response = agent("<a real test question exercising Athena/KB/web search/OpenSearch>")
print(response)
```

## 5. Run it for real

Execute the script above and confirm:
- The MCP server starts and registers all 5 tool groups (verify via
  `start_server(..., verify=True)`'s printed tool list)
- The agent actually calls tools (visible via `PrintingCallbackHandler`'s
  output) and gets real, non-error results back from Athena, Bedrock KB,
  Tavily, and OpenSearch
- `default_` is confirmed absent (expected — Neptune is out of scope here)

## Out of scope / follow-up

Once Neptune connectivity is ready (separate workstream), `default_` should
be added via the real `build_mcp_server(graph_store, vector_store)` path —
not folded into this bare-server approach — and this test script becomes
redundant with (or a stepping stone toward) the full bootstrap function.
