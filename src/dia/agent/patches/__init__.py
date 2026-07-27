"""Aggregates all graphrag-toolkit bugfix patches into a single apply_all().

Each patch is an independent, self-guarded (idempotent) fix for a specific
graphrag-toolkit limitation encountered when running graph queries against
Neptune at production scale — see each submodule's docstring for the
specific problem it fixes. None of these change the agent's behaviour or
tools; they only change how the underlying library talks to Neptune.

Call apply_all() once, before any graph queries are made (i.e. before
building the graph store / MCP server).
"""

from dia.agent.patches import entity_search, neptune_timeout, retry, search_result


def apply_all() -> None:
    """Apply all 4 patches, in the same order they ran in the original
    single-function implementation (search_result -> neptune_timeout ->
    retry -> entity_search). Order isn't currently load-bearing between
    patches, but preserved to avoid introducing any subtle ordering
    assumption.
    """
    search_result.apply()
    neptune_timeout.apply()
    retry.apply()
    entity_search.apply()
