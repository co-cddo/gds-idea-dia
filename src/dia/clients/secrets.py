"""Secrets Manager client.

All secrets are plain strings (not JSON) unless noted. The Tavily secret
in particular must have no trailing whitespace (caused httpx header errors).
"""

from __future__ import annotations

import boto3


def get_secret(
    secret_name: str,
    region: str,
    session: boto3.Session | None = None,
) -> str:
    """Fetch a plain-string secret from AWS Secrets Manager.

    Args:
        secret_name: The name or ARN of the secret.
        region:      AWS region. Defaults to eu-west-2.

    Returns:
        The secret value as a stripped string.

    Raises:
        boto3 ClientError on missing secret or permission denied.
    """
    session = session or boto3.session.Session()
    client = session.client(service_name="secretsmanager", region_name=region)
    return client.get_secret_value(SecretId=secret_name)["SecretString"].strip()
