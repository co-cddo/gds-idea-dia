"""
Smoke-tests the agent's own Neptune connection path (build_graph_store)
over the local SSH tunnel opened by scripts/neptune-tunnel.sh.

Unlike notebooks/neptune_explore.ipynb (which uses the standalone
LocalNeptuneClient), this script exercises the same graph-store code the
agent uses in production, proving that path also works over the tunnel.

Usage:
    ./scripts/neptune-tunnel.sh dev   # run first, in a separate terminal
    uv run python scripts/neptune-agent-tunnel.py

Prerequisites:
    - scripts/neptune-tunnel.sh already running (forwards localhost:8182
      to the real Neptune cluster port).
    - Authenticated to the correct AWS account/profile.
"""

from dia.agent.config import settings
from dia.agent.stores import build_graph_store
from dia.clients.neptune import register_tunnel_host

register_tunnel_host(settings.neptune_endpoint)
graph_store = build_graph_store(settings.neptune_endpoint)

result = graph_store.execute_query("MATCH (n) RETURN labels(n) AS labels, count(n) AS count")
print(result)
