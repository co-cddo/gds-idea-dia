"""Tests for dia.writers — OutputWriter implementations."""

import json

import boto3
import pytest
from moto import mock_aws

from dia.writers.local import LocalOutputWriter
from dia.writers.memory import InMemoryWriter
from dia.writers.s3 import S3OutputWriter

# ---------------------------------------------------------------------------
# InMemoryWriter
# ---------------------------------------------------------------------------


def test_memory_writer_stores_payload():
    writer = InMemoryWriter()

    writer.write("source/docs/a.pdf.json", {"key": "docs/a.pdf", "text": "hello"})

    assert writer.written["source/docs/a.pdf.json"] == {"key": "docs/a.pdf", "text": "hello"}


def test_memory_writer_stores_multiple_keys():
    writer = InMemoryWriter()

    writer.write("a.json", {"text": "one"})
    writer.write("b.json", {"text": "two"})

    assert len(writer.written) == 2
    assert writer.written["a.json"]["text"] == "one"
    assert writer.written["b.json"]["text"] == "two"


def test_memory_writer_overwrites_same_key():
    writer = InMemoryWriter()

    writer.write("a.json", {"text": "first"})
    writer.write("a.json", {"text": "second"})

    assert writer.written["a.json"]["text"] == "second"


def test_memory_writer_starts_empty():
    writer = InMemoryWriter()

    assert writer.written == {}


# ---------------------------------------------------------------------------
# LocalOutputWriter
# ---------------------------------------------------------------------------


def test_local_writer_creates_file(tmp_path):
    writer = LocalOutputWriter(tmp_path)

    writer.write("source/docs/a.pdf.json", {"key": "docs/a.pdf", "text": "hello"})

    output_file = tmp_path / "source" / "docs" / "a.pdf.json"
    assert output_file.exists()


def test_local_writer_content_is_valid_json(tmp_path):
    writer = LocalOutputWriter(tmp_path)
    payload = {"key": "docs/a.pdf", "text": "hello", "chars": 5}

    writer.write("a.json", payload)

    content = json.loads((tmp_path / "a.json").read_text())
    assert content == payload


def test_local_writer_creates_nested_parent_dirs(tmp_path):
    writer = LocalOutputWriter(tmp_path / "nested" / "output")

    writer.write("deep/path/file.json", {"text": "hello"})

    output_file = tmp_path / "nested" / "output" / "deep" / "path" / "file.json"
    assert output_file.exists()


def test_local_writer_accepts_string_path(tmp_path):
    writer = LocalOutputWriter(str(tmp_path))

    writer.write("a.json", {"text": "hello"})

    assert (tmp_path / "a.json").exists()


def test_local_writer_overwrites_existing_file(tmp_path):
    writer = LocalOutputWriter(tmp_path)

    writer.write("a.json", {"text": "first"})
    writer.write("a.json", {"text": "second"})

    content = json.loads((tmp_path / "a.json").read_text())
    assert content["text"] == "second"


def test_local_writer_handles_non_ascii_text(tmp_path):
    writer = LocalOutputWriter(tmp_path)

    writer.write("a.json", {"text": "café résumé"})

    content = json.loads((tmp_path / "a.json").read_text())
    assert content["text"] == "café résumé"


# ---------------------------------------------------------------------------
# S3OutputWriter
# ---------------------------------------------------------------------------

BUCKET = "test-output-bucket"


@pytest.fixture
def s3_client():
    with mock_aws():
        client = boto3.client("s3", region_name="eu-west-2")
        client.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "eu-west-2"},
        )
        yield client


def test_s3_writer_writes_object(s3_client):
    writer = S3OutputWriter(bucket=BUCKET, s3_client=s3_client)

    writer.write("source/docs/a.pdf.json", {"key": "docs/a.pdf", "text": "hello"})

    response = s3_client.get_object(Bucket=BUCKET, Key="source/docs/a.pdf.json")
    payload = json.loads(response["Body"].read())
    assert payload == {"key": "docs/a.pdf", "text": "hello"}


def test_s3_writer_sets_content_type(s3_client):
    writer = S3OutputWriter(bucket=BUCKET, s3_client=s3_client)

    writer.write("a.json", {"text": "hello"})

    response = s3_client.get_object(Bucket=BUCKET, Key="a.json")
    assert response["ContentType"] == "application/json"


def test_s3_writer_overwrites_existing_key(s3_client):
    writer = S3OutputWriter(bucket=BUCKET, s3_client=s3_client)

    writer.write("a.json", {"text": "first"})
    writer.write("a.json", {"text": "second"})

    response = s3_client.get_object(Bucket=BUCKET, Key="a.json")
    payload = json.loads(response["Body"].read())
    assert payload["text"] == "second"


def test_s3_writer_handles_non_ascii_text(s3_client):
    writer = S3OutputWriter(bucket=BUCKET, s3_client=s3_client)

    writer.write("a.json", {"text": "café résumé"})

    response = s3_client.get_object(Bucket=BUCKET, Key="a.json")
    payload = json.loads(response["Body"].read())
    assert payload["text"] == "café résumé"


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_all_writers_satisfy_protocol(tmp_path, s3_client):
    from dia.writers.protocol import OutputWriter

    writers: list[OutputWriter] = [
        InMemoryWriter(),
        LocalOutputWriter(tmp_path),
        S3OutputWriter(bucket=BUCKET, s3_client=s3_client),
    ]

    for writer in writers:
        writer.write("test.json", {"ok": True})
