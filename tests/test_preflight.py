"""Tests for dia.preflight — the checks, with AWS mocked."""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from gds_idea_cdk_constructs import DeploymentEnvironment

from dia.naming import Bucket, Names
from dia.preflight import (
    CROSS_ACCOUNT_ROLE_NAME,
    CheckResult,
    Status,
    check_buckets,
    check_identity,
    check_ledger_table,
    check_neptune,
    check_runtime_config,
    check_source_access,
    cross_account_role_arn,
    run_preflight,
    running_in_ecs_task,
)
from dia.runtime_config import RuntimeConfig, RuntimeConfigError
from dia.types import DataSource, DocumentType

DEV = DeploymentEnvironment.DEVELOPMENT
PROD = DeploymentEnvironment.PRODUCTION
DEV_NAMES = Names(DEV)

CONFIG = RuntimeConfig(
    neptune_endpoint="dia-neptune-dev.cluster-abc.eu-west-2.neptune.amazonaws.com",
    opensearch_endpoint="abc123.eu-west-2.aoss.amazonaws.com",
    cluster_name="shared-cluster",
    task_definition_arn="arn:aws:ecs:eu-west-2:992382722318:task-definition/dia-task-dev:1",
    subnet_ids=["subnet-1"],
    security_group_id="sg-123",
    log_group="/dia/task-dev",
)

SOURCE = DataSource(
    name="test-source",
    document_type=DocumentType.BUSINESS_CASE,
    bucket="source-bucket",
    prefix="files/",
)


def _client_error(code: str = "AccessDenied") -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "denied"}}, "Operation")


# --- identity ---


def test_identity_reports_the_environment_and_role():
    sts = MagicMock()
    sts.get_caller_identity.return_value = {"Account": DEV.value, "Arn": "arn:aws:sts::1:assumed-role/dev/me"}

    result, environment = check_identity(sts)

    assert result.status is Status.OK
    assert "dev" in result.detail
    assert "assumed-role/dev/me" in result.detail
    assert environment is DEV


def test_identity_fails_for_an_unknown_account():
    sts = MagicMock()
    sts.get_caller_identity.return_value = {"Account": "123456789012", "Arn": "arn:aws:sts::1:user/x"}

    result, environment = check_identity(sts)

    assert result.status is Status.FAIL
    assert "123456789012" in result.detail
    assert environment is None


def test_identity_fails_when_sts_cannot_be_called():
    sts = MagicMock()
    sts.get_caller_identity.side_effect = _client_error("ExpiredToken")

    result, environment = check_identity(sts)

    assert result.status is Status.FAIL
    assert "credentials" in result.detail
    assert environment is None


# --- runtime config ---


def test_runtime_config_check_reports_the_parameter_and_endpoint():
    with patch("dia.preflight.RuntimeConfig.load_parameter", return_value=CONFIG):
        result, config = check_runtime_config(DEV_NAMES)

    assert result.status is Status.OK
    assert "dia-runtime-config-dev" in result.detail
    assert CONFIG.neptune_endpoint in result.detail
    assert config is CONFIG


def test_runtime_config_check_fails_with_the_loading_error():
    with patch("dia.preflight.RuntimeConfig.load_parameter", side_effect=RuntimeConfigError("it is missing")):
        result, config = check_runtime_config(DEV_NAMES)

    assert result.status is Status.FAIL
    assert result.detail == "it is missing"
    assert config is None


# --- ledger and buckets ---


def test_ledger_table_check_describes_the_phase_table():
    dynamodb = MagicMock()
    dynamodb.describe_table.return_value = {"Table": {"TableStatus": "ACTIVE"}}

    result = check_ledger_table(DEV_NAMES, dynamodb)

    dynamodb.describe_table.assert_called_once_with(TableName="dia-ledger-dev")
    assert result.status is Status.OK
    assert "ACTIVE" in result.detail


def test_ledger_table_check_fails_when_it_cannot_be_described():
    dynamodb = MagicMock()
    dynamodb.describe_table.side_effect = _client_error("ResourceNotFoundException")

    assert check_ledger_table(DEV_NAMES, dynamodb).status is Status.FAIL


def test_buckets_check_heads_every_bucket():
    s3 = MagicMock()

    result = check_buckets(DEV_NAMES, s3)

    assert result.status is Status.OK
    assert {call.kwargs["Bucket"] for call in s3.head_bucket.call_args_list} == {DEV_NAMES(b) for b in Bucket}


def test_buckets_check_names_each_bucket_that_fails():
    s3 = MagicMock()

    def head(Bucket):  # noqa: N803 - matches the boto3 parameter name
        if Bucket.endswith("batch-dev"):
            raise _client_error("404")

    s3.head_bucket.side_effect = head

    result = check_buckets(DEV_NAMES, s3)

    assert result.status is Status.FAIL
    assert "gds-idea-dia-batch-dev" in result.detail
    assert "text-extracted" not in result.detail


# --- source access ---


def test_cross_account_role_arn_uses_the_production_account():
    assert cross_account_role_arn() == f"arn:aws:iam::{PROD.value}:role/{CROSS_ACCOUNT_ROLE_NAME}"


def test_source_access_in_dev_assumes_the_cross_account_role():
    sts = MagicMock()
    sts.assume_role.return_value = {"Credentials": {"AccessKeyId": "a", "SecretAccessKey": "b", "SessionToken": "c"}}
    s3 = MagicMock()
    s3.list_objects_v2.return_value = {"KeyCount": 1}

    with patch("dia.preflight.boto3.client", return_value=s3) as client:
        result = check_source_access(SOURCE, DEV, sts)

    assert sts.assume_role.call_args.kwargs["RoleArn"] == cross_account_role_arn()
    assert client.call_args.kwargs["aws_session_token"] == "c"
    s3.list_objects_v2.assert_called_once_with(Bucket="source-bucket", Prefix="files/", MaxKeys=1)
    assert result.status is Status.OK
    assert "has objects" in result.detail
    assert cross_account_role_arn() in result.detail


def test_source_access_in_prod_reads_directly():
    sts = MagicMock()
    s3 = MagicMock()
    s3.list_objects_v2.return_value = {"KeyCount": 0}

    with patch("dia.preflight.boto3.client", return_value=s3):
        result = check_source_access(SOURCE, PROD, sts)

    sts.assume_role.assert_not_called()
    assert result.status is Status.OK
    assert "is empty" in result.detail


def test_source_access_fails_when_the_role_cannot_be_assumed():
    sts = MagicMock()
    sts.assume_role.side_effect = _client_error("AccessDenied")

    result = check_source_access(SOURCE, DEV, sts)

    assert result.status is Status.FAIL
    assert "s3://source-bucket/files/" in result.detail


def test_source_access_fails_when_the_listing_is_denied():
    sts = MagicMock()
    sts.assume_role.return_value = {"Credentials": {"AccessKeyId": "a", "SecretAccessKey": "b", "SessionToken": "c"}}
    s3 = MagicMock()
    s3.list_objects_v2.side_effect = _client_error("AccessDenied")

    with patch("dia.preflight.boto3.client", return_value=s3):
        result = check_source_access(SOURCE, DEV, sts)

    assert result.status is Status.FAIL


# --- neptune ---


def _neptune_client(status: str = "healthy") -> MagicMock:
    client = MagicMock()
    client.get_engine_status.return_value = {"status": status}
    return client


def test_neptune_check_reports_the_engine_status():
    factory = MagicMock(return_value=_neptune_client())

    result = check_neptune(CONFIG, connect=lambda host, port: True, client_factory=factory)

    assert result.status is Status.OK
    assert "healthy" in result.detail
    assert factory.call_args.kwargs["endpoint_url"] == f"https://{CONFIG.neptune_endpoint}:8182"


def test_neptune_check_fails_when_it_cannot_connect():
    result = check_neptune(CONFIG, connect=lambda host, port: False)

    assert result.status is Status.FAIL
    assert "security group" in result.detail


def test_neptune_check_fails_when_the_status_call_is_denied():
    client = MagicMock()
    client.get_engine_status.side_effect = _client_error("AccessDeniedException")

    result = check_neptune(CONFIG, connect=lambda host, port: True, client_factory=MagicMock(return_value=client))

    assert result.status is Status.FAIL
    assert "status call failed" in result.detail


# --- running in a task ---


def test_running_in_ecs_task_is_true_only_when_ecs_sets_its_variable(monkeypatch):
    monkeypatch.delenv("ECS_CONTAINER_METADATA_URI_V4", raising=False)
    assert running_in_ecs_task() is False

    monkeypatch.setenv("ECS_CONTAINER_METADATA_URI_V4", "http://169.254.170.2/v4/abc")
    assert running_in_ecs_task() is True


# --- run_preflight ---

_OK = {
    "identity": CheckResult("identity", Status.OK, "x"),
    "runtime config": CheckResult("runtime config", Status.OK, "x"),
    "ledger table": CheckResult("ledger table", Status.OK, "x"),
    "buckets": CheckResult("buckets", Status.OK, "x"),
    "source gats-business-cases": CheckResult("source gats-business-cases", Status.OK, "x"),
    "neptune": CheckResult("neptune", Status.OK, "x"),
}


@contextmanager
def _patched_checks(*, identity=None, config=CONFIG):
    """Replace every check with a canned result; yield the mock for Neptune."""
    identity = identity or (_OK["identity"], DEV)
    with (
        patch("dia.preflight.boto3.client"),
        patch("dia.preflight.check_identity", return_value=identity),
        patch("dia.preflight.check_runtime_config", return_value=(_OK["runtime config"], config)),
        patch("dia.preflight.check_ledger_table", return_value=_OK["ledger table"]),
        patch("dia.preflight.check_buckets", return_value=_OK["buckets"]),
        patch("dia.preflight.check_source_access", return_value=_OK["source gats-business-cases"]),
        patch("dia.preflight.check_neptune", return_value=_OK["neptune"]) as neptune,
    ):
        yield neptune


@pytest.fixture
def local(monkeypatch):
    monkeypatch.delenv("ECS_CONTAINER_METADATA_URI_V4", raising=False)


@pytest.fixture
def in_task(monkeypatch):
    monkeypatch.setenv("ECS_CONTAINER_METADATA_URI_V4", "http://169.254.170.2/v4/abc")


def test_local_preflight_runs_the_checks_local_runs_need_and_not_neptune(local):
    with _patched_checks() as neptune:
        results = run_preflight()

    assert [r.name for r in results] == [
        "identity",
        "runtime config",
        "ledger table",
        "buckets",
        "source gats-business-cases",
    ]
    neptune.assert_not_called()


def test_local_preflight_checks_the_runtime_config(local):
    with _patched_checks(config=None):
        results = run_preflight()

    assert "runtime config" in [r.name for r in results]


def test_task_preflight_also_checks_neptune_last(in_task):
    with _patched_checks() as neptune:
        results = run_preflight()

    assert results[-1].name == "neptune"
    neptune.assert_called_once_with(CONFIG)


def test_task_preflight_skips_neptune_when_the_runtime_config_failed(in_task):
    with _patched_checks(config=None) as neptune:
        results = run_preflight()

    neptune.assert_not_called()
    assert results[-1].name == "neptune"
    assert results[-1].status is Status.SKIP


def test_preflight_skips_everything_else_when_the_environment_is_unknown(local):
    identity = (CheckResult("identity", Status.FAIL, "unknown account"), None)

    with _patched_checks(identity=identity):
        results = run_preflight()

    assert results[0].status is Status.FAIL
    assert [r.status for r in results[1:]] == [Status.SKIP] * 4
    assert "neptune" not in [r.name for r in results]


def test_task_preflight_includes_neptune_among_the_skipped_when_the_environment_is_unknown(in_task):
    identity = (CheckResult("identity", Status.FAIL, "unknown account"), None)

    with _patched_checks(identity=identity):
        results = run_preflight()

    assert [r.status for r in results[1:]] == [Status.SKIP] * 5
    assert results[-1].name == "neptune"
