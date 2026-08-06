"""Live-AWS integration tests for Neptune + the Lexical Graph query engine.

Ported from the exploratory `notebooks/neptune_explore.ipynb` (removed —
superseded by this test).

Unlike `@pytest.mark.integration` elsewhere in this suite (which uses
in-memory mocks and runs in CI), these tests hit **real** AWS infrastructure:

  - Neptune, reached via a local SSH tunnel through a bastion (EICE) —
    see `scripts/neptune-tunnel.sh`.
  - OpenSearch Serverless (AOSS), reached directly over the internet.

They are gated behind the `live_aws` marker and skip automatically unless
explicitly opted into via environment variables, so they never run in CI and
never fail a contributor's local `pytest` run by accident.

To run for real:

    ./scripts/neptune-tunnel.sh dev          # in a separate terminal
    export RUN_LIVE_AWS_TESTS=1
    export NEPTUNE_ENDPOINT=dia-neptune-dev.cluster-xxxx.eu-west-2.neptune.amazonaws.com
    export AOSS_ENDPOINT=https://xxxx.aoss.eu-west-2.on.aws
    export AWS_PROFILE=default               # optional, defaults to "default"
    uv run pytest tests/test_lexical_graph_integration.py -m live_aws -v

Note on `AWS_PROFILE`: the original notebook set `os.environ["aws_profile"]`
(lowercase) intending to configure `graphrag_toolkit`'s `GraphRAGConfig`,
but that config reads the environment variable `AWS_PROFILE` (uppercase) —
so that line was a no-op. This test sets it correctly.
"""

from __future__ import annotations

import os

import pytest

from dia.clients.neptune import LocalNeptuneClient

NEPTUNE_ENDPOINT = os.environ.get("NEPTUNE_ENDPOINT")
AOSS_ENDPOINT = os.environ.get("AOSS_ENDPOINT")
AWS_PROFILE = os.environ.get("AWS_PROFILE", "default")
AWS_REGION = os.environ.get("AWS_REGION", "eu-west-2")
EXTRACTION_MODEL = os.environ.get("EXTRACTION_MODEL", "eu.anthropic.claude-sonnet-4-6")
RESPONSE_MODEL = os.environ.get("RESPONSE_MODEL", "eu.anthropic.claude-sonnet-4-6")
EMBEDDINGS_MODEL = os.environ.get("EMBEDDINGS_MODEL", "amazon.titan-embed-text-v2:0")

_SKIP_REASON = (
    "Requires live AWS infrastructure and a running Neptune SSH tunnel. "
    "Set RUN_LIVE_AWS_TESTS=1, NEPTUNE_ENDPOINT and AOSS_ENDPOINT to run "
    "(see module docstring)."
)
_SHOULD_RUN = os.environ.get("RUN_LIVE_AWS_TESTS") == "1" and NEPTUNE_ENDPOINT and AOSS_ENDPOINT

pytestmark = [
    pytest.mark.live_aws,
    pytest.mark.skipif(not _SHOULD_RUN, reason=_SKIP_REASON),
]


def test_neptune_connectivity():
    """Raw Neptune connectivity through the SSH tunnel.

    The dev cluster is currently empty, so this should return an empty list.
    """
    client = LocalNeptuneClient(endpoint=NEPTUNE_ENDPOINT, profile_name=AWS_PROFILE)

    result = client.query("MATCH (n) RETURN labels(n) AS labels, count(n) AS count")

    assert result == []


def test_lexical_graph_query():
    """End-to-end Lexical Graph query via the AWS toolkit (Neptune + AOSS).

    Exercises both connection paths in one call: Neptune (graph, via the SSH
    tunnel) and AOSS (vector, over the public internet). No assertions on
    the answer content — the bar for now is that it completes without
    raising (e.g. no TLS/certificate errors on either path).
    """
    # graphrag_toolkit's GraphRAGConfig reads these directly from the
    # environment (lazily, on first access) rather than accepting them as
    # constructor args — see graphrag_toolkit.lexical_graph.config.
    os.environ["AWS_REGION"] = AWS_REGION
    os.environ["AWS_PROFILE"] = AWS_PROFILE
    os.environ["EXTRACTION_MODEL"] = EXTRACTION_MODEL
    os.environ["RESPONSE_MODEL"] = RESPONSE_MODEL
    os.environ["EMBEDDINGS_MODEL"] = EMBEDDINGS_MODEL
    os.environ["TOKENIZERS_PARALLELISM"] = "false"

    from graphrag_toolkit.lexical_graph import LexicalGraphQueryEngine
    from graphrag_toolkit.lexical_graph.storage import GraphStoreFactory, VectorStoreFactory

    with (
        GraphStoreFactory.for_graph_store(NEPTUNE_ENDPOINT) as graph_store,
        VectorStoreFactory.for_vector_store(f"aoss://{AOSS_ENDPOINT}") as vector_store,
    ):
        engine = LexicalGraphQueryEngine.for_traversal_based_search(graph_store, vector_store, streaming=True)

        response = engine.query("What are the differences between Neptune Database and Neptune Analytics?")

    assert response is not None
