"""Tests for dia.sources.sidecar_writer: writing a plan to the bucket."""

import csv
from unittest.mock import patch

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from dia.sources.sidecar import Sidecar, to_json
from dia.sources.sidecar_plan import SidecarPlan
from dia.sources.sidecar_writer import BackupError, write_plan

BUCKET = "bucket"
NEW_KEY = "files/new.pdf.metadata.json"
OLD_KEY = "files/old.pdf.metadata.json"
OLD_TEXT = '{"metadataAttributes": {"department": "Home Office"}}'
SIDECAR = Sidecar(document_type="business_case", spend_id="S1")


def _plan(new=(NEW_KEY,), replacements=(OLD_KEY,)) -> SidecarPlan:
    return SidecarPlan(
        rows_read=0,
        test_rows_ignored=0,
        rows_without_documents=0,
        unrecognised_submitters={},
        unreadable_dates={},
        unmatched_departments=[],
        listed=0,
        listed_without_date=0,
        chosen=0,
        not_in_bucket=[],
        chosen_already_labelled=0,
        bucket_not_listed=0,
        outside_run=0,
        outcomes={},
        unchanged=0,
        new={key: SIDECAR for key in new},
        replacements={key: SIDECAR for key in replacements},
        replaced_text={key: OLD_TEXT for key in replacements},
    )


@pytest.fixture
def s3():
    with mock_aws():
        client = boto3.client("s3", region_name="eu-west-2")
        client.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "eu-west-2"})
        client.put_object(Bucket=BUCKET, Key=OLD_KEY, Body=OLD_TEXT.encode())
        yield client


def _text(client, key) -> str:
    return client.get_object(Bucket=BUCKET, Key=key)["Body"].read().decode()


def _write(s3, tmp_path, plan=None, overwrite=False):
    return write_plan(
        s3,
        BUCKET,
        plan or _plan(),
        overwrite=overwrite,
        backup_dir=tmp_path / "backup",
        report_path=tmp_path / "report.csv",
    )


def test_new_labels_are_written_and_existing_ones_are_left_alone_without_overwrite(s3, tmp_path):
    result = _write(s3, tmp_path)

    assert result.written_new == [NEW_KEY]
    assert result.written_replaced == []
    assert _text(s3, NEW_KEY) == to_json(SIDECAR)
    assert _text(s3, OLD_KEY) == OLD_TEXT
    assert not (tmp_path / "backup").exists()


def test_a_label_that_appeared_since_planning_is_never_replaced(s3, tmp_path):
    s3.put_object(Bucket=BUCKET, Key=NEW_KEY, Body=b"someone else's")

    result = _write(s3, tmp_path)

    assert result.skipped_exists == [NEW_KEY]
    assert result.failed == {}
    assert _text(s3, NEW_KEY) == "someone else's"


def test_overwrite_saves_the_old_text_then_replaces_it(s3, tmp_path):
    result = _write(s3, tmp_path, overwrite=True)

    assert result.written_replaced == [OLD_KEY]
    assert _text(s3, OLD_KEY) == to_json(SIDECAR)
    assert (tmp_path / "backup" / OLD_KEY).read_text() == OLD_TEXT


def test_a_failed_backup_stops_the_run_before_anything_is_written(s3, tmp_path):
    with patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
        with pytest.raises(BackupError):
            _write(s3, tmp_path, overwrite=True)

    assert _text(s3, OLD_KEY) == OLD_TEXT
    with pytest.raises(ClientError):
        s3.head_object(Bucket=BUCKET, Key=NEW_KEY)


def test_a_failed_write_is_counted_and_the_rest_go_on(s3, tmp_path):
    original = s3.put_object

    def put(**kwargs):
        if kwargs["Key"] == "files/bad.pdf.metadata.json":
            raise ClientError({"Error": {"Code": "AccessDenied", "Message": "no"}}, "PutObject")
        return original(**kwargs)

    plan = _plan(new=("files/bad.pdf.metadata.json", NEW_KEY), replacements=())
    with patch.object(s3, "put_object", side_effect=put):
        result = _write(s3, tmp_path, plan)

    assert list(result.failed) == ["files/bad.pdf.metadata.json"]
    assert "AccessDenied" in result.failed["files/bad.pdf.metadata.json"]
    assert result.written_new == [NEW_KEY]


def test_a_label_over_the_size_limit_is_a_failure_not_a_crash(s3, tmp_path):
    plan = _plan(replacements=())
    big = Sidecar(document_type="business_case", project_name="x" * 20_000)
    plan = SidecarPlan(**{**plan.__dict__, "new": {NEW_KEY: big}})

    result = _write(s3, tmp_path, plan)

    assert list(result.failed) == [NEW_KEY]


def test_the_report_lists_keys_and_status_and_no_label_content(s3, tmp_path):
    _write(s3, tmp_path, overwrite=True)

    rows = list(csv.reader((tmp_path / "report.csv").open()))
    assert rows == [["label", "status"], [NEW_KEY, "new"], [OLD_KEY, "replaced"]]
