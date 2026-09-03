"""Tests for dia.pipeline.graph_extraction_source — reading Stage 1 output."""

import json

import boto3
import pytest
from moto import mock_aws

from dia.pipeline.graph_extraction_source import (
    LocalTextExtractionOutputSource,
    S3TextExtractionOutputSource,
    TextExtractionOutputSource,
)
from dia.pipeline.models import TextExtractionOutput


def _payload(**overrides) -> dict:
    defaults = dict(
        key="files/report.pdf",
        source_name="gats-business-cases",
        content_type="application/pdf",
        version='"etag-abc123"',
        text="Extracted text.",
        chars=15,
        metadata={"department": "Home Office"},
        extracted_at="2026-07-23T10:00:00+00:00",
        code_version="0.1.20",
    )
    defaults.update(overrides)
    return defaults


# --- LocalTextExtractionOutputSource ---


def test_local_source_returns_empty_list_for_missing_source_dir(tmp_path):
    source = LocalTextExtractionOutputSource(tmp_path)
    assert source.list_outputs("no-such-source") == []


def test_local_source_reads_flat_files(tmp_path):
    source_dir = tmp_path / "gats-business-cases"
    source_dir.mkdir(parents=True)
    (source_dir / "a.json").write_text(json.dumps(_payload(key="a.pdf")), encoding="utf-8")
    (source_dir / "b.json").write_text(json.dumps(_payload(key="b.pdf")), encoding="utf-8")

    source = LocalTextExtractionOutputSource(tmp_path)
    outputs = source.list_outputs("gats-business-cases")

    assert {o.key for o in outputs} == {"a.pdf", "b.pdf"}


def test_local_source_reads_nested_files(tmp_path):
    """LocalOutputWriter mirrors the document key as a nested path
    (e.g. files/report.pdf.json under files/), so listing must recurse."""
    nested_dir = tmp_path / "gats-business-cases" / "files" / "sub"
    nested_dir.mkdir(parents=True)
    (nested_dir / "report.pdf.json").write_text(json.dumps(_payload(key="files/sub/report.pdf")), encoding="utf-8")

    source = LocalTextExtractionOutputSource(tmp_path)
    outputs = source.list_outputs("gats-business-cases")

    assert len(outputs) == 1
    assert outputs[0].key == "files/sub/report.pdf"


def test_local_source_returns_full_text_extraction_output(tmp_path):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "a.json").write_text(json.dumps(_payload()), encoding="utf-8")

    source = LocalTextExtractionOutputSource(tmp_path)
    (output,) = source.list_outputs("src")

    assert isinstance(output, TextExtractionOutput)
    assert output.text == "Extracted text."
    assert output.metadata == {"department": "Home Office"}
    assert output.code_version == "0.1.20"


def test_local_source_accepts_string_base_dir(tmp_path):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "a.json").write_text(json.dumps(_payload()), encoding="utf-8")

    source = LocalTextExtractionOutputSource(str(tmp_path))
    outputs = source.list_outputs("src")

    assert len(outputs) == 1


# --- S3TextExtractionOutputSource ---

BUCKET = "test-text-extracted-bucket"


@pytest.fixture
def s3_client():
    with mock_aws():
        client = boto3.client("s3", region_name="eu-west-2")
        client.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "eu-west-2"})
        yield client


def test_s3_source_returns_empty_list_for_missing_prefix(s3_client):
    source = S3TextExtractionOutputSource(bucket=BUCKET, s3_client=s3_client)
    assert source.list_outputs("no-such-source") == []


def test_s3_source_reads_matching_objects(s3_client):
    s3_client.put_object(
        Bucket=BUCKET, Key="gats-business-cases/a.pdf.json", Body=json.dumps(_payload(key="a.pdf")).encode()
    )
    s3_client.put_object(
        Bucket=BUCKET,
        Key="gats-business-cases/files/b.pdf.json",
        Body=json.dumps(_payload(key="files/b.pdf")).encode(),
    )
    # Different source prefix — must not be picked up.
    s3_client.put_object(Bucket=BUCKET, Key="other-source/c.pdf.json", Body=json.dumps(_payload(key="c.pdf")).encode())

    source = S3TextExtractionOutputSource(bucket=BUCKET, s3_client=s3_client)
    outputs = source.list_outputs("gats-business-cases")

    assert {o.key for o in outputs} == {"a.pdf", "files/b.pdf"}


def test_s3_source_ignores_non_json_objects(s3_client):
    s3_client.put_object(Bucket=BUCKET, Key="src/a.json", Body=json.dumps(_payload(key="a.pdf")).encode())
    s3_client.put_object(Bucket=BUCKET, Key="src/.keep", Body=b"")

    source = S3TextExtractionOutputSource(bucket=BUCKET, s3_client=s3_client)
    outputs = source.list_outputs("src")

    assert len(outputs) == 1
    assert outputs[0].key == "a.pdf"


def test_s3_source_returns_full_text_extraction_output(s3_client):
    s3_client.put_object(Bucket=BUCKET, Key="src/a.json", Body=json.dumps(_payload()).encode())

    source = S3TextExtractionOutputSource(bucket=BUCKET, s3_client=s3_client)
    (output,) = source.list_outputs("src")

    assert isinstance(output, TextExtractionOutput)
    assert output.text == "Extracted text."
    assert output.metadata == {"department": "Home Office"}


# --- Protocol conformance ---


def test_both_sources_satisfy_protocol(tmp_path, s3_client):
    sources: list[TextExtractionOutputSource] = [
        LocalTextExtractionOutputSource(tmp_path),
        S3TextExtractionOutputSource(bucket=BUCKET, s3_client=s3_client),
    ]
    for source in sources:
        assert source.list_outputs("any-source") == []
