"""Tests for dia.sources — S3DocumentSource and known sources."""

import boto3
import pytest
from moto import mock_aws

from dia.sources import KNOWN_SOURCES, S3DocumentSource, get_source
from dia.sources.protocol import DocumentSource
from dia.types import DataSource, DocumentReference, DocumentType


@pytest.fixture
def data_source() -> DataSource:
    return DataSource(
        document_type=DocumentType.BUSINESS_CASE,
        bucket="test-bucket",
        prefix="docs/",
    )


@pytest.fixture
def s3_client():
    with mock_aws():
        client = boto3.client("s3", region_name="eu-west-2")
        yield client


@pytest.fixture
def populated_bucket(s3_client, data_source):
    """Create a bucket with a mix of files."""
    s3_client.create_bucket(
        Bucket=data_source.bucket,
        CreateBucketConfiguration={"LocationConstraint": "eu-west-2"},
    )
    # Documents that should be listed
    s3_client.put_object(Bucket=data_source.bucket, Key="docs/report.pdf", Body=b"pdf-content")
    s3_client.put_object(Bucket=data_source.bucket, Key="docs/memo.docx", Body=b"docx-content")
    s3_client.put_object(Bucket=data_source.bucket, Key="docs/sub/nested.pdf", Body=b"nested-pdf")
    # Files that should be filtered out
    s3_client.put_object(Bucket=data_source.bucket, Key="docs/data.csv", Body=b"csv-data")
    s3_client.put_object(Bucket=data_source.bucket, Key="other/report.pdf", Body=b"wrong-prefix")
    return s3_client


# --- S3DocumentSource satisfies protocol ---


def test_s3_document_source_satisfies_protocol():
    """S3DocumentSource is structurally compatible with DocumentSource protocol."""
    source: DocumentSource = S3DocumentSource(
        data_source=DataSource(document_type=DocumentType.SR_BIDS, bucket="x", prefix=""),
        s3_client=None,
    )
    assert hasattr(source, "list_documents")
    assert hasattr(source, "load_document")


# --- list_documents ---


def test_list_documents_returns_matching_files(populated_bucket, data_source):
    source = S3DocumentSource(data_source=data_source, s3_client=populated_bucket)
    refs = source.list_documents()

    keys = {r.key for r in refs}
    assert keys == {"docs/report.pdf", "docs/memo.docx", "docs/sub/nested.pdf"}


def test_list_documents_filters_by_extension(populated_bucket, data_source):
    source = S3DocumentSource(data_source=data_source, s3_client=populated_bucket)
    refs = source.list_documents()

    # csv should not be included
    keys = {r.key for r in refs}
    assert "docs/data.csv" not in keys


def test_list_documents_respects_prefix(populated_bucket, data_source):
    source = S3DocumentSource(data_source=data_source, s3_client=populated_bucket)
    refs = source.list_documents()

    # File outside prefix should not appear
    keys = {r.key for r in refs}
    assert "other/report.pdf" not in keys


def test_list_documents_empty_bucket(s3_client, data_source):
    s3_client.create_bucket(
        Bucket=data_source.bucket,
        CreateBucketConfiguration={"LocationConstraint": "eu-west-2"},
    )
    source = S3DocumentSource(data_source=data_source, s3_client=s3_client)
    refs = source.list_documents()

    assert refs == []


def test_list_documents_correct_content_types(populated_bucket, data_source):
    source = S3DocumentSource(data_source=data_source, s3_client=populated_bucket)
    refs = source.list_documents()

    by_key = {r.key: r.content_type for r in refs}
    assert by_key["docs/report.pdf"] == "application/pdf"
    assert by_key["docs/memo.docx"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_list_documents_populates_version_from_etag(populated_bucket, data_source):
    source = S3DocumentSource(data_source=data_source, s3_client=populated_bucket)
    refs = source.list_documents()

    for ref in refs:
        assert ref.version != "", f"{ref.key} should have a version (ETag)"


def test_list_documents_custom_extensions(s3_client):
    data_source = DataSource(
        document_type=DocumentType.CONTRACT_FINDER,
        bucket="test-bucket",
        prefix="",
        file_extensions=(".csv",),
    )
    s3_client.create_bucket(
        Bucket="test-bucket",
        CreateBucketConfiguration={"LocationConstraint": "eu-west-2"},
    )
    s3_client.put_object(Bucket="test-bucket", Key="data.csv", Body=b"csv")
    s3_client.put_object(Bucket="test-bucket", Key="report.pdf", Body=b"pdf")

    source = S3DocumentSource(data_source=data_source, s3_client=s3_client)
    refs = source.list_documents()

    assert len(refs) == 1
    assert refs[0].key == "data.csv"


# --- load_document ---


def test_load_document_returns_bytes(populated_bucket, data_source):
    source = S3DocumentSource(data_source=data_source, s3_client=populated_bucket)
    ref = DocumentReference(key="docs/report.pdf", content_type="application/pdf", version="")

    content = source.load_document(ref)

    assert content == b"pdf-content"


def test_load_document_different_file(populated_bucket, data_source):
    source = S3DocumentSource(data_source=data_source, s3_client=populated_bucket)
    ref = DocumentReference(
        key="docs/memo.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        version="",
    )

    content = source.load_document(ref)

    assert content == b"docx-content"


# --- data_source property ---


def test_data_source_property(data_source):
    source = S3DocumentSource(data_source=data_source, s3_client=None)
    assert source.data_source is data_source


# --- known sources ---


def test_known_sources_not_empty():
    assert len(KNOWN_SOURCES) > 0


def test_known_sources_all_have_valid_document_types():
    for name, ds in KNOWN_SOURCES.items():
        assert isinstance(ds.document_type, DocumentType), f"{name} has invalid document_type"


def test_get_source_returns_correct_source():
    source = get_source("gats-business-cases")
    assert source.document_type == DocumentType.BUSINESS_CASE
    assert source.cross_account is True


def test_get_source_sr_bids():
    source = get_source("sr-bids-2025")
    assert source.document_type == DocumentType.SR_BIDS
    assert source.cross_account is False


def test_get_source_unknown_raises():
    with pytest.raises(KeyError):
        get_source("does-not-exist")
