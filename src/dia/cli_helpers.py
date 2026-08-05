"""CLI helpers for environment resolution and resource naming.

Resolves the deployment environment from the authenticated AWS account
using gds-idea-cdk-constructs. Single source of truth for account→environment
mapping — no hardcoded account maps in this repo.
"""

import boto3
import typer
from gds_idea_cdk_constructs import DeploymentEnvironment


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


def resolve_ledger_table() -> str:
    """Derive the DynamoDB ledger table name from the active environment.

    Returns:
        Table name following the pattern: dia-ledger-{phase}
    """
    env = detect_environment()
    return f"dia-ledger-{env.short_name}"


def resolve_text_output_bucket() -> str:
    """Derive the text-extracted output S3 bucket name from the active environment.

    Returns:
        Bucket name following the pattern: gds-idea-dia-text-extracted-{phase}
    """
    env = detect_environment()
    return f"gds-idea-dia-text-extracted-{env.short_name}"
