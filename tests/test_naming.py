"""Tests for dia.naming — resource and bucket names, and agreement with the CDK config."""

import pytest
from gds_idea_cdk_constructs import DeploymentEnvironment

from config import AppConfig
from dia.naming import Bucket, Names

ENVIRONMENTS = [
    (DeploymentEnvironment.DEVELOPMENT, "dev"),
    (DeploymentEnvironment.PRODUCTION, "prod"),
]


@pytest.mark.parametrize("environment,phase", ENVIRONMENTS)
def test_phase_comes_from_the_environment(environment, phase):
    assert Names(environment).phase == phase


@pytest.mark.parametrize("environment,phase", ENVIRONMENTS)
def test_calling_names_builds_project_name_with_phase(environment, phase):
    names = Names(environment)

    assert names("ledger") == f"dia-ledger-{phase}"
    assert names("SecretStack") == f"dia-SecretStack-{phase}"


@pytest.mark.parametrize("environment,phase", ENVIRONMENTS)
@pytest.mark.parametrize("bucket", list(Bucket))
def test_bucket_names_include_team_project_and_phase(environment, phase, bucket):
    assert Names(environment)(bucket) == f"gds-idea-dia-{bucket.value}-{phase}"


@pytest.mark.parametrize("bucket", list(Bucket))
def test_a_bucket_name_as_a_plain_string_is_rejected(bucket):
    with pytest.raises(ValueError, match=f"Bucket.{bucket.name}"):
        Names(DeploymentEnvironment.DEVELOPMENT)(bucket.value)


def test_a_resource_that_only_contains_a_bucket_name_is_allowed():
    assert Names(DeploymentEnvironment.DEVELOPMENT)("batch-inference") == "dia-batch-inference-dev"


def test_every_bucket_is_distinct():
    names = Names(DeploymentEnvironment.DEVELOPMENT)

    assert len({names(b) for b in Bucket}) == len(Bucket)


@pytest.mark.parametrize("environment,phase", ENVIRONMENTS)
def test_app_config_uses_the_same_names(environment, phase):
    config = AppConfig(environment=environment)

    assert config.names == Names(environment)
    assert config.tavily_secret == f"dia-tavily-{phase}"
    assert config.neptune_endpoint_secret == f"dia-neptune-endpoint-{phase}"
    assert config.aoss_endpoint_secret == f"dia-aoss-endpoint-{phase}"
    assert config.kb_arns == f"dia-kb-arns-{phase}"
