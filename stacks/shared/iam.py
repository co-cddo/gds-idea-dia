"""IAM helpers shared by more than one stack."""

from __future__ import annotations

from aws_cdk import aws_iam as iam
from constructs import Construct

from config import AppConfig


def permissions_boundary(scope: Construct, construct_id: str, *, config: AppConfig) -> iam.IManagedPolicy:
    """The account's `DenyUserPermissionsPolicy`, for use as a role's permissions boundary.

    The policy allows everything except creating and changing IAM users and
    access keys, so it removes nothing a pipeline role needs. It is the same
    boundary the CI deploy roles carry. To stop putting a boundary on this
    project's roles, remove the calls to this function.

    Args:
        scope: The construct to import the policy into.
        construct_id: ID for the imported policy. Must be unique within `scope`.
        config: The CDK config, for the account number.

    Returns:
        The imported managed policy.
    """
    return iam.ManagedPolicy.from_managed_policy_arn(
        scope,
        construct_id,
        f"arn:aws:iam::{config.account_number}:policy/DenyUserPermissionsPolicy",
    )
