"""Patch: reduce Neptune's query read_timeout from 600s to 90s.

The graphrag-toolkit hardcodes a 600-second (10 minute) read_timeout when
building the botocore config for Neptune requests, and passing read_timeout
via the config kwarg directly causes a duplicate-keyword error — so it can't
be overridden by passing a different config in. This patch wraps the
library's create_config() and merges in a 90s override after the fact.

90s gives legitimate queries time to complete while ensuring a hung/expensive
traversal fails fast, so the agent can escalate to a throttled retrieval mode
rather than blocking for 10 minutes on one query.
"""

import graphrag_toolkit.lexical_graph.storage.graph.neptune_graph_stores as _neptune_mod
from botocore.config import Config as BotocoreConfig


def apply() -> None:
    """Patch neptune_graph_stores.create_config in place.

    Idempotent: safe to call more than once — guarded by checking for
    `_unpatched_create_config`, which only gets set on the first call.
    """
    if not hasattr(_neptune_mod, "_unpatched_create_config"):
        _neptune_mod._unpatched_create_config = _neptune_mod.create_config

        _original_create_config = _neptune_mod._unpatched_create_config

        def _patched_create_config(config=None):
            cfg = _original_create_config(config)
            return cfg.merge(BotocoreConfig(read_timeout=90))

        _neptune_mod.create_config = _patched_create_config
