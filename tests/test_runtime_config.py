"""Tests for dia.runtime_config — loading and validating the runtime config parameter."""

import json
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError, NoCredentialsError
from gds_idea_cdk_constructs import DeploymentEnvironment
from pydantic import ValidationError

from dia.naming import Names
from dia.runtime_config import RUNTIME_CONFIG_ENV_VAR, RuntimeConfig, RuntimeConfigError

DEV_NAMES = Names(DeploymentEnvironment.DEVELOPMENT)

VALID = {
    "neptune_endpoint": "dia-neptune-dev.cluster-abc.eu-west-2.neptune.amazonaws.com",
    "neptune_port": 8182,
    "opensearch_endpoint": "abc123.eu-west-2.aoss.amazonaws.com",
    "cluster_name": "shared-cluster",
    "task_definition_arn": "arn:aws:ecs:eu-west-2:992382722318:task-definition/dia-task-dev:1",
    "subnet_ids": ["subnet-1", "subnet-2"],
    "security_group_id": "sg-123",
    "log_group": "/dia/task-dev",
    "cross_account_role_arn": "arn:aws:iam::588077357019:role/some-cross-account-role",
}


@pytest.fixture(autouse=True)
def _no_pointer_variable(monkeypatch):
    monkeypatch.delenv(RUNTIME_CONFIG_ENV_VAR, raising=False)


def _ssm(value: str) -> MagicMock:
    ssm = MagicMock()
    ssm.get_parameter.return_value = {"Parameter": {"Value": value}}
    return ssm


# --- parameter name ---


def test_parameter_name_is_built_from_names_when_the_variable_is_not_set():
    assert RuntimeConfig.parameter_name(DEV_NAMES) == "dia-runtime-config-dev"


def test_parameter_name_comes_from_the_variable_when_set(monkeypatch):
    monkeypatch.setenv(RUNTIME_CONFIG_ENV_VAR, "custom-name")

    assert RuntimeConfig.parameter_name(DEV_NAMES) == "custom-name"


def test_parameter_name_needs_names_or_the_variable():
    with pytest.raises(RuntimeConfigError, match=RUNTIME_CONFIG_ENV_VAR):
        RuntimeConfig.parameter_name()


# --- load ---


def test_load_reads_and_validates_the_parameter():
    ssm = _ssm(json.dumps(VALID))

    config = RuntimeConfig.load(DEV_NAMES, ssm_client=ssm)

    ssm.get_parameter.assert_called_once_with(Name="dia-runtime-config-dev")
    assert config.neptune_endpoint == VALID["neptune_endpoint"]
    assert config.subnet_ids == ["subnet-1", "subnet-2"]


def test_load_reads_the_parameter_named_by_the_variable(monkeypatch):
    monkeypatch.setenv(RUNTIME_CONFIG_ENV_VAR, "custom-name")
    ssm = _ssm(json.dumps(VALID))

    RuntimeConfig.load(ssm_client=ssm)

    ssm.get_parameter.assert_called_once_with(Name="custom-name")


def test_load_defaults_the_neptune_port():
    without_port = {k: v for k, v in VALID.items() if k != "neptune_port"}

    config = RuntimeConfig.load(DEV_NAMES, ssm_client=_ssm(json.dumps(without_port)))

    assert config.neptune_port == 8182


def test_load_explains_a_missing_parameter():
    ssm = MagicMock()
    ssm.get_parameter.side_effect = ClientError(
        {"Error": {"Code": "ParameterNotFound", "Message": "nope"}}, "GetParameter"
    )

    with pytest.raises(
        RuntimeConfigError, match="Could not read the runtime config parameter 'dia-runtime-config-dev'"
    ):
        RuntimeConfig.load(DEV_NAMES, ssm_client=ssm)


def test_load_explains_a_failure_that_is_not_a_client_error():
    ssm = MagicMock()
    ssm.get_parameter.side_effect = NoCredentialsError()

    with pytest.raises(RuntimeConfigError, match="Could not read the runtime config parameter"):
        RuntimeConfig.load(DEV_NAMES, ssm_client=ssm)


def test_load_parameter_reads_the_named_parameter():
    ssm = _ssm(json.dumps(VALID))

    config = RuntimeConfig.load_parameter("some-name", ssm_client=ssm)

    ssm.get_parameter.assert_called_once_with(Name="some-name")
    assert config.cluster_name == "shared-cluster"


def test_load_explains_a_parameter_that_is_not_json():
    with pytest.raises(RuntimeConfigError, match="not valid JSON"):
        RuntimeConfig.load(DEV_NAMES, ssm_client=_ssm("{not json"))


def test_load_names_every_missing_field():
    bad = {k: v for k, v in VALID.items() if k not in {"cluster_name", "log_group"}}

    with pytest.raises(RuntimeConfigError) as excinfo:
        RuntimeConfig.load(DEV_NAMES, ssm_client=_ssm(json.dumps(bad)))

    assert "cluster_name" in str(excinfo.value)
    assert "log_group" in str(excinfo.value)


def test_load_rejects_unknown_fields():
    with pytest.raises(RuntimeConfigError, match="extra_field"):
        RuntimeConfig.load(DEV_NAMES, ssm_client=_ssm(json.dumps({**VALID, "extra_field": 1})))


# --- validation ---


@pytest.mark.parametrize(
    "endpoint",
    ["https://host.example.com", "host.example.com:8182", "host.example.com/path", ""],
)
def test_neptune_endpoint_must_be_a_hostname_only(endpoint):
    with pytest.raises(RuntimeConfigError, match="neptune_endpoint"):
        RuntimeConfig.load(DEV_NAMES, ssm_client=_ssm(json.dumps({**VALID, "neptune_endpoint": endpoint})))


def test_opensearch_endpoint_loses_a_leading_https_scheme_and_trailing_slash():
    value = {**VALID, "opensearch_endpoint": "https://abc123.eu-west-2.aoss.amazonaws.com/"}

    config = RuntimeConfig.load(DEV_NAMES, ssm_client=_ssm(json.dumps(value)))

    assert config.opensearch_endpoint == "abc123.eu-west-2.aoss.amazonaws.com"


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://host.example.com",
        "aoss://host.example.com",
        "host.example.com:443",
        "host.example.com/path",
        "",
        "https://",
    ],
)
def test_opensearch_endpoint_must_be_a_hostname_only(endpoint):
    with pytest.raises(RuntimeConfigError, match="opensearch_endpoint"):
        RuntimeConfig.load(DEV_NAMES, ssm_client=_ssm(json.dumps({**VALID, "opensearch_endpoint": endpoint})))


@pytest.mark.parametrize("port", [0, 70000])
def test_neptune_port_must_be_a_valid_port(port):
    with pytest.raises(RuntimeConfigError, match="neptune_port"):
        RuntimeConfig.load(DEV_NAMES, ssm_client=_ssm(json.dumps({**VALID, "neptune_port": port})))


def test_subnet_ids_must_not_be_empty():
    with pytest.raises(RuntimeConfigError, match="subnet_ids"):
        RuntimeConfig.load(DEV_NAMES, ssm_client=_ssm(json.dumps({**VALID, "subnet_ids": []})))


def test_config_is_frozen():
    config = RuntimeConfig.model_validate(VALID)

    with pytest.raises(ValidationError):
        config.cluster_name = "other"


# --- cross-account role ---


def test_cross_account_role_arn_defaults_to_none_when_absent():
    without_role = {k: v for k, v in VALID.items() if k != "cross_account_role_arn"}

    config = RuntimeConfig.load(DEV_NAMES, ssm_client=_ssm(json.dumps(without_role)))

    assert config.cross_account_role_arn is None
