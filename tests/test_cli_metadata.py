"""Tests for `dia pipeline metadata`: the dry run that says what labelling GATS documents would do."""

import re
from unittest.mock import patch

import boto3
import pytest
from botocore.exceptions import ClientError
from gds_idea_cdk_constructs import DeploymentEnvironment
from moto import mock_aws
from typer.testing import CliRunner

from dia.cli import app
from dia.runtime_config import RuntimeConfig, RuntimeConfigError
from dia.sources.definitions import SOURCES

runner = CliRunner()

BUCKET = SOURCES["gats_business_cases"].location.bucket.prod
ROLE = "arn:aws:iam::000000000000:role/fake-cross-account-role"

OLD_EXPORT = (
    "\ufeffCO_SpendID,CO_OrganisationSubmitter,CO_CaseSubmitDate,CO_CS_Files,CO_CS_CaseName\n"
    'S1,Home Office,2026-05-01,"a.pdf,b.docx",Case one\n'
    'S2,Home Ofice,2026-04-01,"c.pdf,ghost.pdf",Case two\n'
    "S3,Home Office,,,\n"
)
NEW_EXPORT = (
    "CO_SpendID,CO_OrganisationSubmitter,CO_CaseSubmitDate,CO_I_Documents,CO_I_Name\n"
    "N1,Home Office,2026-09-01,n.pdf,New\n"
)

BUCKET_KEYS = [
    "files/a.pdf",
    "files/b.docx",
    "files/c.pdf",
    "files/z.pdf",
    "files/n.pdf",
    "files/a.pdf.metadata.json",
    "files/old.json",
]


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _count(output: str, label: str) -> int:
    """The number on the line that starts with `label`."""
    (line,) = [line for line in _plain(output).splitlines() if line.strip().startswith(label)]
    return int(re.search(r"(\d+)", line.split(":", 1)[1]).group(1))


@pytest.fixture
def s3():
    with mock_aws():
        client = boto3.client("s3", region_name="eu-west-2")
        client.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "eu-west-2"})
        client.put_object(Bucket=BUCKET, Key="spend-controls-raw-data/old.csv", Body=OLD_EXPORT.encode())
        client.put_object(Bucket=BUCKET, Key="spend-controls-raw-data/gas/new.csv", Body=NEW_EXPORT.encode())
        for key in BUCKET_KEYS:
            client.put_object(Bucket=BUCKET, Key=key, Body=b"x")
        yield client


@pytest.fixture
def prod(s3):
    with patch("dia.cli_helpers.detect_environment", return_value=DeploymentEnvironment.PRODUCTION):
        yield s3


def _run(*args):
    return runner.invoke(app, ["pipeline", "metadata", *args])


def _snapshot(client):
    """Every key, with its ETag and modified time: changes if anything is written, replaced or deleted."""
    pages = client.get_paginator("list_objects_v2").paginate(Bucket=BUCKET)
    return sorted((o["Key"], o["ETag"], o["LastModified"]) for p in pages for o in p.get("Contents", []))


# --- the counts ---


def test_it_prints_the_counts_for_an_export_by_bare_file_name(prod):
    result = _run("--export", "old.csv")

    assert result.exit_code == 0, result.output
    assert "spend-controls-raw-data/old.csv" in result.output
    assert _count(result.output, "rows read") == 3
    assert _count(result.output, "rows with no documents") == 1
    assert _count(result.output, "documents listed") == 4
    assert _count(result.output, "documents with no date") == 0
    assert _count(result.output, "documents chosen") == 4
    assert _count(result.output, "not in the bucket") == 1
    assert _count(result.output, "already have a label") == 1
    assert _count(result.output, "documents the export does not list") == 2
    assert _count(result.output, "new labels only") == 2
    assert _count(result.output, "with --overwrite") == 3


def test_it_names_the_unrecognised_submitters_and_nothing_else_from_the_export(prod):
    result = _run("--export", "old.csv")
    assert "unrecognised submitters:        1 rows, 1 names" in result.output
    assert "Home Ofice: 1" in result.output
    for private in ("Case one", "Case two", "S1", "S2", "a.pdf", "b.docx", "ghost.pdf"):
        assert private not in result.output


def test_latest_reads_the_newest_export_in_the_gas_folder(prod):
    result = _run("--export", "latest")

    assert result.exit_code == 0, result.output
    assert "spend-controls-raw-data/gas/new.csv" in result.output
    assert _count(result.output, "rows read") == 1


def test_the_limit_counts_documents_and_takes_the_newest(prod):
    result = _run("--export", "old.csv", "--limit", "1")
    assert _count(result.output, "documents listed") == 4
    assert _count(result.output, "documents chosen") == 1


def test_departments_are_applied_and_ones_that_match_nothing_are_named(prod):
    result = _run("--export", "old.csv", "--departments", "home office, Nowhere Office")

    assert _count(result.output, "documents chosen") == 2
    assert _count(result.output, "departments that matched nothing") == 1
    assert "    Nowhere Office" in result.output


# --- it never writes ---


def test_a_run_changes_nothing_in_the_bucket(prod):
    before = _snapshot(prod)

    result = _run("--export", "old.csv")

    assert result.exit_code == 0, result.output
    assert _snapshot(prod) == before
    assert "nothing was written" in result.output


def test_a_run_only_makes_read_calls(prod):
    calls = []
    original = boto3.client("s3", region_name="eu-west-2")._make_api_call.__func__

    def record(self, operation_name, api_params):
        calls.append(operation_name)
        return original(self, operation_name, api_params)

    with patch("botocore.client.BaseClient._make_api_call", record):
        result = _run("--export", "old.csv")

    assert result.exit_code == 0, result.output
    assert calls
    assert set(calls) <= {"GetObject", "ListObjectsV2"}, calls


# --- bad input and failures ---


def test_a_limit_below_one_is_a_usage_error(prod):
    result = _run("--export", "old.csv", "--limit", "0")
    assert result.exit_code == 2
    assert "--limit" in _plain(result.output)


def test_departments_with_no_names_is_a_usage_error(prod):
    result = _run("--export", "old.csv", "--departments", " , ")
    assert result.exit_code == 2
    assert "at least one department" in _plain(result.output)


def test_the_export_option_is_required(prod):
    assert _run().exit_code == 2


def test_a_missing_export_is_a_clear_error_not_a_traceback(prod):
    result = _run("--export", "missing.csv")
    assert result.exit_code == 1
    assert "does not exist" in result.output
    assert "Traceback" not in result.output


def test_latest_with_no_csv_in_the_gas_folder_is_a_clear_error(prod):
    prod.delete_object(Bucket=BUCKET, Key="spend-controls-raw-data/gas/new.csv")
    result = _run("--export", "latest")
    assert result.exit_code == 1
    assert "no CSV export" in result.output


def test_access_denied_on_the_export_is_a_clear_error(prod):
    denied = ClientError({"Error": {"Code": "AccessDenied", "Message": "Access Denied"}}, "GetObject")
    with (
        patch.object(prod, "get_object", side_effect=denied),
        patch("dia.preflight.source_s3_client", return_value=prod),
    ):
        result = _run("--export", "old.csv")

    assert result.exit_code == 1
    assert "could not read from s3://" in result.output
    assert "AccessDenied" in result.output


# --- reading in dev goes through the cross-account role ---


def _dev_config(role=ROLE):
    return RuntimeConfig(
        neptune_endpoint="neptune.example",
        opensearch_endpoint="search.example",
        cluster_name="cluster",
        task_definition_arn="arn:task",
        subnet_ids=["subnet-1"],
        security_group_id="sg-1",
        log_group="/dia-task-dev",
        cross_account_role_arn=role,
    )


@pytest.fixture
def dev(s3):
    with patch("dia.cli_helpers.detect_environment", return_value=DeploymentEnvironment.DEVELOPMENT):
        yield s3


def test_in_dev_the_role_from_the_runtime_config_is_assumed_with_its_own_session_name(dev):
    with (
        patch("dia.runtime_config.RuntimeConfig.load", return_value=_dev_config()),
        patch("dia.preflight.source_s3_client", return_value=dev) as client,
    ):
        result = _run("--export", "old.csv")

    assert result.exit_code == 0, result.output
    assert client.call_args.args[0] == ROLE
    assert client.call_args.kwargs["session_name"] == "dia-metadata"
    assert "through the cross-account role" in result.output


def test_in_prod_no_role_is_used(prod):
    with patch("dia.preflight.source_s3_client", return_value=prod) as client:
        result = _run("--export", "old.csv")

    assert result.exit_code == 0, result.output
    assert client.call_args.args[0] is None
    assert "(production)" in result.output


def test_in_dev_a_runtime_config_with_no_role_is_an_error(dev):
    with patch("dia.runtime_config.RuntimeConfig.load", return_value=_dev_config(role=None)):
        result = _run("--export", "old.csv")

    assert result.exit_code == 1
    assert "runtime config has none" in result.output


def test_in_dev_an_unreadable_runtime_config_is_a_clear_error(dev):
    with patch("dia.runtime_config.RuntimeConfig.load", side_effect=RuntimeConfigError("parameter not found")):
        result = _run("--export", "old.csv")

    assert result.exit_code == 1
    assert "parameter not found" in result.output
