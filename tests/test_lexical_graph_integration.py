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
    export AWS_PROFILE=<your-profile>        # required — see note below
    uv run pytest tests/test_lexical_graph_integration.py -m live_aws -v

Only two exports are required. Everything else is either resolved
automatically or has a sensible default:

  - Neptune/AOSS endpoints are looked up live via CloudFormation (the same
    way `scripts/neptune-tunnel.sh` already finds the Neptune one) — no
    copy-pasting hostnames, and nothing is ever written to disk. To point at
    something non-standard instead, `export NEPTUNE_ENDPOINT=...` /
    `export AOSS_ENDPOINT=...` — these always win over the lookup.
  - `AWS_REGION`, model IDs, and the deployment phase used for the
    CloudFormation lookup all come from `dia.clients.config.AwsSettings`,
    which can also be set via a local, git-ignored `.env` file instead of
    repeated `export`s — see that module's docstring.

Note on `AWS_PROFILE`: this is required, not guessed. If it's unset, the
`live_aws_setup` fixture fails immediately with the list of profiles found
in your `~/.aws` config, rather than silently falling back to a profile
named "default" (which may not exist, or may not be the login you meant).
On a successful run, the fixture also prints the resolved AWS account and
ARN — worth checking, since `scripts/neptune-tunnel.sh` opens the tunnel
using your ambient AWS login, which can silently differ from `AWS_PROFILE`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import boto3
import pytest

from dia.clients.cloudformation import resolve_stack_output
from dia.clients.config import aws_settings
from dia.clients.neptune import LocalNeptuneClient

_SKIP_REASON = (
    "Requires live AWS infrastructure and a running Neptune SSH tunnel. "
    "Set RUN_LIVE_AWS_TESTS=1 to run (see module docstring)."
)
_SHOULD_RUN = os.environ.get("RUN_LIVE_AWS_TESTS") == "1"

pytestmark = [
    pytest.mark.live_aws,
    pytest.mark.skipif(not _SHOULD_RUN, reason=_SKIP_REASON),
    # graphrag_toolkit's own import-time compatibility shim calls the
    # deprecated asyncio.get_event_loop() — harmless, but only worth
    # silencing here, where it actually fires (see graphrag_toolkit's
    # lexical_graph/__init__.py), not project-wide.
    pytest.mark.filterwarnings("ignore:There is no current event loop:DeprecationWarning"),
]


@dataclass
class LiveAwsSetup:
    """Everything a live-AWS test needs: a verified identity + endpoints."""

    identity: dict
    neptune_endpoint: str
    aoss_endpoint: str


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


def _resolve_endpoint(session: boto3.Session, env_var: str, stack_name: str, output_key: str) -> str:
    """Return `env_var` if set (manual override); otherwise look it up live."""
    override = os.environ.get(env_var)
    if override:
        return override

    try:
        return resolve_stack_output(session, stack_name, output_key)
    except ValueError as e:
        pytest.fail(
            f"Could not resolve {env_var} — tried CloudFormation stack "
            f"'{stack_name}', output '{output_key}'.\n"
            f"  {e}\n"
            f"Override: export {env_var}=<endpoint>",
            pytrace=False,
        )


@pytest.fixture(scope="session", autouse=True)
def live_aws_setup(request) -> LiveAwsSetup:
    """Fail fast with a clear reason if AWS credentials aren't usable.

    Runs before any test in this module. Requires `AWS_PROFILE` to be set
    explicitly — it is never guessed — and checks it actually resolves to a
    real, logged-in AWS identity via `sts:GetCallerIdentity`. Then resolves
    the Neptune/AOSS endpoints (manual override, else live CloudFormation
    lookup). On success, reports which profile/account/region/identity and
    endpoints are in use, since `scripts/neptune-tunnel.sh` uses ambient
    credentials for the SSH tunnel while this fixture's profile is used to
    sign requests — a mismatch between the two is otherwise silent and
    looks like a network error.
    """
    available = _available_profiles()

    if not aws_settings.aws_profile:
        pytest.fail(
            "AWS_PROFILE is not set — these live tests will not guess which "
            "AWS login to use.\n"
            f"Available profiles: {', '.join(available) or '<none found>'}\n"
            "Run:  export AWS_PROFILE=<name>\n"
            "      aws sso login --profile <name>",
            pytrace=False,
        )

    try:
        session = boto3.Session(profile_name=aws_settings.aws_profile, region_name=aws_settings.aws_region)
        identity = session.client("sts").get_caller_identity()
    except Exception as e:  # noqa: BLE001 - any failure here means creds aren't usable
        pytest.fail(
            "Could not resolve AWS credentials for these live tests.\n"
            f"  AWS_PROFILE : {aws_settings.aws_profile}\n"
            f"  AWS_REGION  : {aws_settings.aws_region}\n"
            f"  error       : {type(e).__name__}: {e}\n"
            f"  available   : {', '.join(available) or '<none found>'}\n"
            f"Run:  aws sso login --profile {aws_settings.aws_profile}",
            pytrace=False,
        )

    neptune_endpoint = _resolve_endpoint(
        session, "NEPTUNE_ENDPOINT", f"dia-neptune-{aws_settings.phase}", "NeptuneEndpoint"
    )
    aoss_endpoint = _resolve_endpoint(
        session, "AOSS_ENDPOINT", f"dia-opensearch-{aws_settings.phase}", "AossCollectionEndpoint"
    )

    aws_settings.export_to_environ()
    os.environ["TOKENIZERS_PARALLELISM"] = "false"

    reporter = request.config.pluginmanager.get_plugin("terminalreporter")
    reporter.write_line(
        f"live_aws: profile={aws_settings.aws_profile} account={identity['Account']} "
        f"region={aws_settings.aws_region}\n"
        f"          arn={identity['Arn']}\n"
        f"          neptune={neptune_endpoint}\n"
        f"          aoss={aoss_endpoint}"
    )
    return LiveAwsSetup(identity=identity, neptune_endpoint=neptune_endpoint, aoss_endpoint=aoss_endpoint)


def test_neptune_connectivity(live_aws_setup: LiveAwsSetup):
    """Raw Neptune connectivity through the SSH tunnel.

    The dev cluster is currently empty, so this should return an empty list.
    """
    client = LocalNeptuneClient(endpoint=live_aws_setup.neptune_endpoint, profile_name=aws_settings.aws_profile)

    result = client.query("MATCH (n) RETURN labels(n) AS labels, count(n) AS count")

    assert result == []


def test_lexical_graph_query(live_aws_setup: LiveAwsSetup):
    """End-to-end Lexical Graph query via the AWS toolkit (Neptune + AOSS).

    Exercises both connection paths in one call: Neptune (graph, via the SSH
    tunnel) and AOSS (vector, over the public internet). No assertions on
    the answer content — the bar for now is that it completes without
    raising (e.g. no TLS/certificate errors on either path).
    """
    # Env vars for graphrag_toolkit's GraphRAGConfig are set by the
    # `live_aws_setup` autouse fixture, before any test in this module runs.
    from graphrag_toolkit.lexical_graph import LexicalGraphQueryEngine
    from graphrag_toolkit.lexical_graph.storage import GraphStoreFactory, VectorStoreFactory

    with (
        GraphStoreFactory.for_graph_store(live_aws_setup.neptune_endpoint) as graph_store,
        VectorStoreFactory.for_vector_store(f"aoss://{live_aws_setup.aoss_endpoint}") as vector_store,
    ):
        engine = LexicalGraphQueryEngine.for_traversal_based_search(graph_store, vector_store, streaming=True)

        response = engine.query("What are the differences between Neptune Database and Neptune Analytics?")

    assert response is not None
