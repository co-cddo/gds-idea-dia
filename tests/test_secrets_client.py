"""Tests for dia.clients.secrets — AWS Secrets Manager client."""

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from dia.clients.secrets import get_secret

REGION = "eu-west-2"


@pytest.fixture
def secretsmanager_client():
    with mock_aws():
        client = boto3.client("secretsmanager", region_name=REGION)
        yield client


def test_get_secret_returns_value(secretsmanager_client):
    secretsmanager_client.create_secret(Name="dia-tavily-dev", SecretString="tvly-abc123")

    value = get_secret("dia-tavily-dev", region=REGION)

    assert value == "tvly-abc123"


def test_get_secret_strips_whitespace(secretsmanager_client):
    secretsmanager_client.create_secret(Name="dia-tavily-dev", SecretString="  tvly-abc123\n")

    value = get_secret("dia-tavily-dev", region=REGION)

    assert value == "tvly-abc123"


def test_get_secret_returns_raw_json_string_unparsed(secretsmanager_client):
    """kb-arns is a multi-key JSON secret — get_secret() is the plain-string
    primitive and should hand back the raw string, not parse it."""
    secretsmanager_client.create_secret(
        Name="dia-kb-arns-dev",
        SecretString='{"kb_gats_business_cases": "arn:aws:bedrock:..."}',
    )

    value = get_secret("dia-kb-arns-dev", region=REGION)

    assert value == '{"kb_gats_business_cases": "arn:aws:bedrock:..."}'


def test_get_secret_missing_secret_raises(secretsmanager_client):
    with pytest.raises(ClientError):
        get_secret("dia-does-not-exist-dev", region=REGION)


def test_get_secret_uses_provided_session(secretsmanager_client):
    secretsmanager_client.create_secret(Name="dia-tavily-dev", SecretString="tvly-abc123")
    session = boto3.session.Session()

    value = get_secret("dia-tavily-dev", region=REGION, session=session)

    assert value == "tvly-abc123"


def test_get_secret_wrong_region_raises(secretsmanager_client):
    secretsmanager_client.create_secret(Name="dia-tavily-dev", SecretString="tvly-abc123")

    with pytest.raises(ClientError):
        get_secret("dia-tavily-dev", region="us-east-1")
