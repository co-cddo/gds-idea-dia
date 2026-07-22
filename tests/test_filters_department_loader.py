"""Tests for dia.filters.department_loader — S3 CSV metadata loading."""

import boto3
import pytest
from moto import mock_aws

from dia.filters.department_loader import (
    find_latest_key,
    load_csv_from_s3,
    load_latest_csv_from_s3,
)

BUCKET = "test-metadata-bucket"


@pytest.fixture
def s3_client():
    with mock_aws():
        client = boto3.client("s3", region_name="eu-west-2")
        client.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "eu-west-2"},
        )
        yield client


# ---------------------------------------------------------------------------
# load_csv_from_s3
# ---------------------------------------------------------------------------


def test_loads_csv_rows(s3_client):
    csv_body = "department,alb,filenames\nHome Office,,a.pdf\nHMRC,,b.pdf\n"
    s3_client.put_object(Bucket=BUCKET, Key="metadata.csv", Body=csv_body.encode())

    rows = load_csv_from_s3(BUCKET, "metadata.csv", s3_client=s3_client)

    assert len(rows) == 2
    assert rows[0] == {"department": "Home Office", "alb": "", "filenames": "a.pdf"}
    assert rows[1] == {"department": "HMRC", "alb": "", "filenames": "b.pdf"}


def test_loads_empty_csv():
    with mock_aws():
        client = boto3.client("s3", region_name="eu-west-2")
        client.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "eu-west-2"})
        client.put_object(Bucket=BUCKET, Key="empty.csv", Body=b"department,alb,filenames\n")

        rows = load_csv_from_s3(BUCKET, "empty.csv", s3_client=client)

        assert rows == []


# ---------------------------------------------------------------------------
# find_latest_key
# ---------------------------------------------------------------------------


def test_finds_latest_key_among_multiple(s3_client):
    s3_client.put_object(Bucket=BUCKET, Key="exports/2025-01-01.csv", Body=b"old")
    s3_client.put_object(Bucket=BUCKET, Key="exports/2025-06-01.csv", Body=b"newer")
    s3_client.put_object(Bucket=BUCKET, Key="exports/2025-03-01.csv", Body=b"middle")

    latest = find_latest_key(BUCKET, "exports/", s3_client=s3_client)

    assert latest == "exports/2025-06-01.csv"


def test_single_file_is_latest(s3_client):
    s3_client.put_object(Bucket=BUCKET, Key="exports/only.csv", Body=b"data")

    latest = find_latest_key(BUCKET, "exports/", s3_client=s3_client)

    assert latest == "exports/only.csv"


def test_no_files_raises(s3_client):
    with pytest.raises(FileNotFoundError, match="No files found"):
        find_latest_key(BUCKET, "nonexistent/", s3_client=s3_client)


# ---------------------------------------------------------------------------
# load_latest_csv_from_s3
# ---------------------------------------------------------------------------


def test_loads_latest_csv(s3_client):
    old_csv = "CO_OrganisationSubmitter,CO_SpendID\nOld Dept,CS-001\n"
    new_csv = "CO_OrganisationSubmitter,CO_SpendID\nHome Office,CS-100\n"

    s3_client.put_object(Bucket=BUCKET, Key="gats/2025-01-01.csv", Body=old_csv.encode())
    s3_client.put_object(Bucket=BUCKET, Key="gats/2025-06-01.csv", Body=new_csv.encode())

    rows = load_latest_csv_from_s3(BUCKET, "gats/", s3_client=s3_client)

    assert len(rows) == 1
    assert rows[0]["CO_OrganisationSubmitter"] == "Home Office"
    assert rows[0]["CO_SpendID"] == "CS-100"


def test_load_latest_csv_no_files_raises(s3_client):
    with pytest.raises(FileNotFoundError):
        load_latest_csv_from_s3(BUCKET, "gats/", s3_client=s3_client)
