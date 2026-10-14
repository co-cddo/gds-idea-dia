"""CLI helpers for environment resolution.

Resolves the deployment environment from the authenticated AWS account
using gds-idea-cdk-constructs. Single source of truth for account→environment
mapping — no hardcoded account maps in this repo. Resource names come from
`dia.naming`.
"""

import boto3
import typer
from gds_idea_cdk_constructs import DeploymentEnvironment

from dia.naming import Names


def detect_environment() -> DeploymentEnvironment:
    """Resolve deployment environment from the authenticated AWS account.

    Makes an STS GetCallerIdentity call to discover the account number,
    then maps it to a DeploymentEnvironment via the constructs library.

    Raises:
        typer.Exit: If the account is not recognised.
    """
    try:
        account_id = boto3.client("sts", region_name="eu-west-2").get_caller_identity()["Account"]
    except Exception as e:
        typer.echo(f"Error: Failed to resolve AWS account: {e}")
        raise typer.Exit(code=1) from None

    try:
        return DeploymentEnvironment.from_account_id(account_id)
    except ValueError:
        typer.echo(f"Error: Unrecognised AWS account {account_id}. Check your credentials.")
        raise typer.Exit(code=1) from None


def current_names() -> Names:
    """Names for the AWS account of the active credentials.

    Raises:
        typer.Exit: If the account is not recognised.
    """
    return Names(detect_environment())
