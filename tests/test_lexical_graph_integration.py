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
    export AWS_PROFILE=<your-profile>        # required — see note below
    uv run pytest tests/test_lexical_graph_integration.py -m live_aws -v

Note on `AWS_PROFILE`: this is required, not guessed. If it's unset, the
`aws_identity` fixture fails immediately with the list of profiles found in
your `~/.aws` config, rather than silently falling back to a profile named
"default" (which may not exist, or may not be the login you meant). On a
successful run, the fixture also prints the resolved AWS account and ARN —
worth checking, since `scripts/neptune-tunnel.sh` opens the tunnel using
your ambient AWS login, which can silently differ from `AWS_PROFILE`.

(The original notebook set `os.environ["aws_profile"]` (lowercase) intending
to configure `graphrag_toolkit`'s `GraphRAGConfig`, but that config reads the
environment variable `AWS_PROFILE` (uppercase) — so that line was a no-op.
This test sets it correctly.)
"""

from __future__ import annotations

import os

import boto3
import pytest

from dia.clients.neptune import LocalNeptuneClient

NEPTUNE_ENDPOINT = os.environ.get("NEPTUNE_ENDPOINT")
AOSS_ENDPOINT = os.environ.get("AOSS_ENDPOINT")
AWS_PROFILE = os.environ.get("AWS_PROFILE")
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


def _available_profiles() -> list[str]:
    """List profile names found in `~/.aws`.

    A bare `boto3.Session()` reads the ambient `AWS_PROFILE` env var while
    setting itself up, and raises immediately if it names a profile that
    doesn't exist — before we get a chance to report that exact problem.
    Sidestep that by unsetting it just for this lookup.
    """
    saved = os.environ.pop("AWS_PROFILE", None)
    try:
        return boto3.Session().available_profiles
    finally:
        if saved is not None:
            os.environ["AWS_PROFILE"] = saved


@pytest.fixture(scope="session", autouse=True)
def aws_identity(request):
    """Fail fast with a clear reason if AWS credentials aren't usable.

    Runs before any test in this module. Requires `AWS_PROFILE` to be set
    explicitly — it is never guessed — and checks it actually resolves to a
    real, logged-in AWS identity via `sts:GetCallerIdentity`. On success,
    reports which profile/account/region/identity is in use, since
    `scripts/neptune-tunnel.sh` uses ambient credentials for the SSH tunnel
    while this fixture's profile is used to sign requests — a mismatch
    between the two is otherwise silent and looks like a network error.
    """
    available = _available_profiles()

    if not AWS_PROFILE:
        pytest.fail(
            "AWS_PROFILE is not set — these live tests will not guess which "
            "AWS login to use.\n"
            f"Available profiles: {', '.join(available) or '<none found>'}\n"
            "Run:  export AWS_PROFILE=<name>\n"
            "      aws sso login --profile <name>",
            pytrace=False,
        )

    try:
        session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
        identity = session.client("sts").get_caller_identity()
    except Exception as e:  # noqa: BLE001 - any failure here means creds aren't usable
        pytest.fail(
            "Could not resolve AWS credentials for these live tests.\n"
            f"  AWS_PROFILE : {AWS_PROFILE}\n"
            f"  AWS_REGION  : {AWS_REGION}\n"
            f"  error       : {type(e).__name__}: {e}\n"
            f"  available   : {', '.join(available) or '<none found>'}\n"
            f"Run:  aws sso login --profile {AWS_PROFILE}",
            pytrace=False,
        )

    # graphrag_toolkit's GraphRAGConfig reads these directly from the
    # environment (lazily, on first access, and caches the result) rather
    # than accepting them as constructor args — see
    # graphrag_toolkit.lexical_graph.config. Set them here, before any test
    # runs, so nothing reads a stale/unset value first.
    os.environ["AWS_REGION"] = AWS_REGION
    os.environ["AWS_PROFILE"] = AWS_PROFILE
    os.environ["EXTRACTION_MODEL"] = EXTRACTION_MODEL
    os.environ["RESPONSE_MODEL"] = RESPONSE_MODEL
    os.environ["EMBEDDINGS_MODEL"] = EMBEDDINGS_MODEL
    os.environ["TOKENIZERS_PARALLELISM"] = "false"

    reporter = request.config.pluginmanager.get_plugin("terminalreporter")
    reporter.write_line(
        f"live_aws: profile={AWS_PROFILE} account={identity['Account']} region={AWS_REGION}\n"
        f"          arn={identity['Arn']}\n"
        f"          neptune={NEPTUNE_ENDPOINT}"
    )
    return identity


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
    # Env vars for graphrag_toolkit's GraphRAGConfig are set by the
    # `aws_identity` autouse fixture, before any test in this module runs.
    from graphrag_toolkit.lexical_graph import LexicalGraphQueryEngine
    from graphrag_toolkit.lexical_graph.storage import GraphStoreFactory, VectorStoreFactory

    with (
        GraphStoreFactory.for_graph_store(NEPTUNE_ENDPOINT) as graph_store,
        VectorStoreFactory.for_vector_store(f"aoss://{AOSS_ENDPOINT}") as vector_store,
    ):
        engine = LexicalGraphQueryEngine.for_traversal_based_search(graph_store, vector_store, streaming=True)

        response = engine.query("What are the differences between Neptune Database and Neptune Analytics?")

    assert response is not None
