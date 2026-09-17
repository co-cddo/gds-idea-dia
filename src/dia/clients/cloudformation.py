"""Look up CloudFormation stack outputs — e.g. Neptune/AOSS endpoints.

Infrastructure endpoints (Neptune, OpenSearch Serverless) are already
published as named CloudFormation outputs by the stacks that create them
(see `stacks/neptune.py`, `stacks/opensearch.py`). `scripts/neptune-tunnel.sh`
already looks up the Neptune one this way to open its SSH tunnel.

Resolving endpoints this way — instead of a developer finding them once
and pasting them into a file or a doc — means: nothing is ever written to
disk, the value can't go stale after a redeploy, and AWS itself enforces
who's allowed to see it.
"""

from __future__ import annotations

import boto3
from botocore.exceptions import ClientError


def resolve_stack_output(session: boto3.Session, stack_name: str, output_key: str) -> str:
    """Fetch a single named output value from a CloudFormation stack.

    Args:
        session: An authenticated boto3 session.
        stack_name: The CloudFormation stack name, e.g. "dia-neptune-dev".
        output_key: The output's key, e.g. "NeptuneEndpoint".

    Returns:
        The output's value.

    Raises:
        ValueError: If the stack doesn't exist, or has no output with that
            key. Callers decide how to present this (e.g. pytest.fail with
            an override command).
    """
    cloudformation = session.client("cloudformation")

    try:
        response = cloudformation.describe_stacks(StackName=stack_name)
    except ClientError as e:
        raise ValueError(f"Could not describe CloudFormation stack '{stack_name}': {e}") from e

    outputs = response["Stacks"][0].get("Outputs", [])
    for output in outputs:
        if output["OutputKey"] == output_key:
            return output["OutputValue"]

    raise ValueError(f"Stack '{stack_name}' has no output named '{output_key}'")
