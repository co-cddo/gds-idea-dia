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
from dia.sources.gats_sidecars import OLD_EXPORT_KEY

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
    assert _count(result.output, "documents the exports do not list") == 2
    assert _count(result.output, "new labels only") == 4
    assert _count(result.output, "with --overwrite") == 5


def test_it_names_the_unrecognised_submitters_and_nothing_else_from_the_export(prod):
    result = _run("--export", "old.csv")
    assert re.search(r"unrecognised submitters:\s+1 rows, 1 names", result.output)
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


def test_with_no_export_the_last_older_export_and_the_newest_one_are_read(prod):
    prod.put_object(Bucket=BUCKET, Key=OLD_EXPORT_KEY, Body=OLD_EXPORT.encode())

    result = _run()

    assert result.exit_code == 0, result.output
    assert OLD_EXPORT_KEY in result.output
    assert "spend-controls-raw-data/gas/new.csv" in result.output
    assert _count(result.output, "rows read") == 4


def test_giving_an_export_replaces_the_defaults(prod):
    result = _run("--export", "old.csv")
    assert "spend-controls-raw-data/gas/new.csv" not in result.output
    assert _count(result.output, "rows read") == 3


def test_a_missing_default_export_is_a_clear_error(prod):
    result = _run()
    assert result.exit_code == 1
    assert "does not exist" in result.output


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


# --- dates, as the real exports write them ---

REAL_FORMATS_EXPORT = (
    "CO_SpendID,CO_OrganisationSubmitter,CO_SpendStartDate,CO_DT_SpendStartDate,CO_CaseSubmitDate,CO_CS_Files\n"
    'S1,HM Revenue & Customs,01 April 2024,,,"a.pdf"\n'
    'S2,Home Office,,01 April 2025,,"b.docx"\n'
    'S3,Home Office,,,30-Mar-26,"c.pdf"\n'
)
BAD_DATES_EXPORT = (
    "CO_SpendID,CO_OrganisationSubmitter,CO_CaseSubmitDate,CO_CS_Files\n"
    'S1,Home Office,soon,"a.pdf"\n'
    'S2,Home Office,soon,"b.docx"\n'
    'S3,Home Office,,"c.pdf"\n'
)


def test_the_real_date_formats_in_all_three_columns_are_read(prod):
    prod.put_object(Bucket=BUCKET, Key="spend-controls-raw-data/real.csv", Body=REAL_FORMATS_EXPORT.encode())

    result = _run("--export", "real.csv")

    assert result.exit_code == 0, result.output
    assert _count(result.output, "documents listed") == 3
    assert _count(result.output, "documents with no date") == 0
    assert _count(result.output, "dates that could not be read") == 0
    assert _count(result.output, "unrecognised submitters") == 0


def test_dates_that_cannot_be_read_are_counted_apart_from_empty_ones_with_examples(prod):
    prod.put_object(Bucket=BUCKET, Key="spend-controls-raw-data/bad.csv", Body=BAD_DATES_EXPORT.encode())

    result = _run("--export", "bad.csv")

    assert result.exit_code == 0, result.output
    assert _count(result.output, "documents with no date") == 3
    assert re.search(r"dates that could not be read:\s+2 rows, 1 values", result.output)
    assert "    soon: 2" in result.output


def test_every_count_starts_in_the_same_column(prod):
    result = _run("--export", "old.csv")

    counts = [line for line in _plain(result.output).splitlines() if re.match(r"  [a-z].*:\s+\S", line)]
    assert len(counts) >= 10
    columns = {re.match(r"  [^:]+:\s*", line).end() for line in counts}
    assert columns == {39}


def test_rows_from_test_submitters_are_ignored_and_counted_in_the_output(prod):
    body = OLD_EXPORT + 'S9,GATS_test,2026-05-01,"z.pdf",Test case\nS8,00_Test,,"y.pdf",Test case\n'
    prod.put_object(Bucket=BUCKET, Key="spend-controls-raw-data/with-tests.csv", Body=body.encode())

    result = _run("--export", "with-tests.csv")

    assert result.exit_code == 0, result.output
    assert _count(result.output, "rows read") == 5
    assert _count(result.output, "rows ignored as test data") == 2
    assert _count(result.output, "documents listed") == 4
    assert "GATS_test" not in result.output


# --- what each document would get ---


def test_it_prints_what_every_document_in_the_bucket_would_get(prod):
    result = _run("--export", "old.csv")

    # a, b, c are listed; ghost is not in the bucket; z and n are not listed and have no label.
    assert _count(result.output, "label from the export") == 3
    assert _count(result.output, "basic label") == 2
    assert _count(result.output, "label rebuilt from its case") == 0
    assert _count(result.output, "no label yet") == 0
    assert _count(result.output, "left alone") == 0


def test_a_pptx_with_no_source_waits_and_a_pdf_with_no_source_gets_a_basic_label(prod):
    prod.put_object(Bucket=BUCKET, Key="files/slides.pptx", Body=b"x")

    result = _run("--export", "old.csv")

    assert _count(result.output, "no label yet") == 1
    assert _count(result.output, "basic label") == 2


def test_an_old_label_whose_case_is_in_the_export_is_rebuilt_from_the_case(prod):
    prod.put_object(Bucket=BUCKET, Key="files/extra.pdf", Body=b"x")
    prod.put_object(
        Bucket=BUCKET,
        Key="files/extra.pdf.metadata.json",
        Body=b'{"metadataAttributes": {"document_type": "business_case", "spend_id": "S1"}}',
    )

    result = _run("--export", "old.csv")

    assert _count(result.output, "label rebuilt from its case") == 1


def test_a_second_run_over_labels_that_are_already_correct_would_write_nothing(prod):
    from dia.sources.gats_sidecars import list_bucket_keys, read_export
    from dia.sources.sidecar import to_json
    from dia.sources.sidecar_plan import plan

    rows = read_export(prod, BUCKET, "spend-controls-raw-data/old.csv")
    keys = list_bucket_keys(prod, BUCKET, "files/")
    first = plan(rows, keys, prefix="files/")
    for key, sidecar in {**first.new, **first.replacements}.items():
        prod.put_object(Bucket=BUCKET, Key=key, Body=to_json(sidecar).encode())

    result = _run("--export", "old.csv")

    assert _count(result.output, "new labels only") == 0
    assert _count(result.output, "with --overwrite") == 0
    assert _count(result.output, "already correct") >= 4


# --- a limit and the trial ---


def test_the_trial_labels_only_the_chosen_files_and_leaves_the_rest_alone(prod):
    result = _run("--export", "latest", "--limit", "1")

    assert result.exit_code == 0, result.output
    assert _count(result.output, "label from the export") == 1
    assert _count(result.output, "basic label") == 0
    assert _count(result.output, "left alone") > 0
    assert _count(result.output, "new labels only") == 1


def test_a_limit_over_several_exports_says_which_dates_are_used(prod):
    prod.put_object(Bucket=BUCKET, Key=OLD_EXPORT_KEY, Body=OLD_EXPORT.encode())

    result = _run("--limit", "2")

    assert "--limit takes the newest by date across all these exports" in _plain(result.output)
    assert "use --export latest" in _plain(result.output)


def test_a_limit_over_one_export_has_no_note(prod):
    assert "Note:" not in _run("--export", "latest", "--limit", "2").output


# --- a newer older export than the default ---


def test_a_newer_older_export_than_the_default_is_a_warning_when_the_defaults_are_used(prod):
    prod.put_object(Bucket=BUCKET, Key=OLD_EXPORT_KEY, Body=OLD_EXPORT.encode())
    newer = ["spend-controls-raw-data/DataExport_99999999999999.csv"]

    with patch("dia.sources.gats_sidecars.newer_old_exports", return_value=newer):
        result = _run()

    assert result.exit_code == 0, result.output
    assert "Warning: spend-controls-raw-data/DataExport_99999999999999.csv is newer" in result.output


def test_no_warning_when_the_default_is_the_newest_older_export(prod):
    prod.put_object(Bucket=BUCKET, Key=OLD_EXPORT_KEY, Body=OLD_EXPORT.encode())
    assert "Warning" not in _run().output


def test_no_warning_check_is_made_when_an_export_is_given(prod):
    with patch("dia.sources.gats_sidecars.newer_old_exports", return_value=["x.csv"]) as check:
        result = _run("--export", "old.csv")
    assert "Warning" not in result.output
    check.assert_not_called()


# --- the report ---


def test_the_report_lists_every_document_with_what_it_gets(prod, tmp_path):
    import csv

    report = tmp_path / "out" / "metadata.csv"

    result = _run("--export", "old.csv", "--report", str(report))

    assert result.exit_code == 0, result.output
    assert f"Report written to {report}" in result.output
    rows = list(csv.DictReader(report.open(encoding="utf-8")))
    by_document = {row["document"]: (row["outcome"], row["label"]) for row in rows}
    assert by_document["files/a.pdf"] == ("from_export", "replaced")
    assert by_document["files/b.docx"] == ("from_export", "new")
    assert by_document["files/z.pdf"] == ("basic_label", "new")
    assert by_document["files/ghost.pdf"] == ("listed_but_not_in_bucket", "none")
    assert "files/old.json" not in by_document


def test_the_report_names_documents_but_the_screen_does_not(prod, tmp_path):
    report = tmp_path / "metadata.csv"
    result = _run("--export", "old.csv", "--report", str(report))
    assert "z.pdf" in report.read_text()
    assert "z.pdf" not in result.output


def test_no_report_is_written_unless_asked_for(prod, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _run("--export", "old.csv")
    assert list(tmp_path.iterdir()) == []


def test_progress_is_not_mixed_into_the_counts(prod):
    result = _run("--export", "old.csv")
    assert "Reading 1 existing labels..." in result.output
    assert result.stdout.count("Reading") == 0
