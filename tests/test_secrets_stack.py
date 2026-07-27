import json

import pytest
from gds_idea_cdk_constructs import DeploymentEnvironment

from stacks.secrets import SecretsStack


@pytest.mark.parametrize(
    "environment,phase",
    [
        (DeploymentEnvironment.DEVELOPMENT, "dev"),
        (DeploymentEnvironment.PRODUCTION, "prod"),
    ],
)
def test_creates_four_secrets(synth, environment, phase):
    template = synth(SecretsStack, environment)
    template.resource_count_is("AWS::SecretsManager::Secret", 4)


@pytest.mark.parametrize(
    "environment,phase",
    [
        (DeploymentEnvironment.DEVELOPMENT, "dev"),
        (DeploymentEnvironment.PRODUCTION, "prod"),
    ],
)
def test_secret_names_follow_pattern(synth, environment, phase):
    template = synth(SecretsStack, environment)
    resources = template.find_resources("AWS::SecretsManager::Secret")
    for resource in resources.values():
        name = resource["Properties"]["Name"]
        assert name.startswith("dia-")
        assert name.endswith(f"-{phase}")


@pytest.mark.parametrize(
    "environment,phase,purpose",
    [
        (DeploymentEnvironment.DEVELOPMENT, "dev", "tavily"),
        (DeploymentEnvironment.DEVELOPMENT, "dev", "neptune-endpoint"),
        (DeploymentEnvironment.DEVELOPMENT, "dev", "aoss-endpoint"),
        (DeploymentEnvironment.DEVELOPMENT, "dev", "kb-arns"),
        (DeploymentEnvironment.PRODUCTION, "prod", "tavily"),
        (DeploymentEnvironment.PRODUCTION, "prod", "neptune-endpoint"),
        (DeploymentEnvironment.PRODUCTION, "prod", "aoss-endpoint"),
        (DeploymentEnvironment.PRODUCTION, "prod", "kb-arns"),
    ],
)
def test_expected_secret_exists(synth, environment, phase, purpose):
    template = synth(SecretsStack, environment)
    template.has_resource_properties(
        "AWS::SecretsManager::Secret",
        {"Name": f"dia-{purpose}-{phase}"},
    )


def test_kb_arns_secret_has_expected_keys(synth):
    template = synth(SecretsStack)
    resources = template.find_resources("AWS::SecretsManager::Secret")
    kb_arns_resource = next(r for r in resources.values() if r["Properties"]["Name"] == "dia-kb-arns-dev")
    secret_string = json.loads(kb_arns_resource["Properties"]["SecretString"])
    assert set(secret_string.keys()) == {
        "kb_gats_business_cases",
        "kb_sr25_bids",
        "kb_sr21_bids",
        "kb_nao_reports",
        "kb_efficiency_reports",
    }


def test_single_value_secrets_have_no_hardcoded_value(synth):
    """Tavily/Neptune/AOSS secrets are created empty (GenerateSecretString) —
    real values are set out-of-band via `aws secretsmanager put-secret-value`,
    never embedded in the CDK template.
    """
    template = synth(SecretsStack)
    resources = template.find_resources("AWS::SecretsManager::Secret")
    for purpose in ("dia-tavily-dev", "dia-neptune-endpoint-dev", "dia-aoss-endpoint-dev"):
        resource = next(r for r in resources.values() if r["Properties"]["Name"] == purpose)
        assert "GenerateSecretString" in resource["Properties"]
        assert "SecretString" not in resource["Properties"]


def test_creates_three_set_secret_command_outputs(synth):
    template = synth(SecretsStack)
    outputs = template.to_json().get("Outputs", {})
    assert set(outputs.keys()) == {
        "SetTavilySecretCommand",
        "SetNeptuneEndpointCommand",
        "SetAossEndpointCommand",
    }
