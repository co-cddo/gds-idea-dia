"""Tests for dia.pipeline.text_extraction — TextExtractionRunner."""

import json

import boto3
import pytest
from moto import mock_aws

from dia.config import TextExtractionConfig
from dia.document_types import DocumentType
from dia.ledger.memory import InMemoryLedger
from dia.pipeline import TextExtractionRunner
from dia.types import DataSource, DocumentReference

OUTPUT_BUCKET = "test-text-extracted"
SOURCE_BUCKET = "test-source-bucket"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class InMemorySource:
    """In-memory document source for testing."""

    def __init__(self, data_source: DataSource, documents: dict[str, bytes]) -> None:
        self._data_source = data_source
        self._documents = documents

    @property
    def data_source(self) -> DataSource:
        return self._data_source

    def list_documents(self) -> list[DocumentReference]:
        refs = []
        for key in sorted(self._documents.keys()):
            if key.lower().endswith(".pdf"):
                ct = "application/pdf"
            elif key.lower().endswith(".docx"):
                ct = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            else:
                ct = "application/octet-stream"
            refs.append(DocumentReference(key=key, content_type=ct, version="v1"))
        return refs

    def load_document(self, ref: DocumentReference) -> bytes:
        return self._documents[ref.key]


class PdfOnlyFilter:
    """Filter that only allows PDF files through."""

    def filter(self, refs: list[DocumentReference]) -> list[DocumentReference]:
        return [r for r in refs if r.key.lower().endswith(".pdf")]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def data_source():
    return DataSource(
        name="test-source",
        document_type=DocumentType.BUSINESS_CASE,
        bucket=SOURCE_BUCKET,
        prefix="docs/",
    )


@pytest.fixture
def config():
    return TextExtractionConfig(batch_size=2, max_concurrency=5)


@pytest.fixture
def s3_setup():
    """Create moto S3 with source + output buckets."""
    with mock_aws():
        client = boto3.client("s3", region_name="eu-west-2")
        client.create_bucket(
            Bucket=SOURCE_BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "eu-west-2"},
        )
        client.create_bucket(
            Bucket=OUTPUT_BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "eu-west-2"},
        )
        # Upload fake documents
        client.put_object(Bucket=SOURCE_BUCKET, Key="docs/a.pdf", Body=b"fake pdf a")
        client.put_object(Bucket=SOURCE_BUCKET, Key="docs/b.pdf", Body=b"fake pdf b")
        client.put_object(Bucket=SOURCE_BUCKET, Key="docs/c.pdf", Body=b"fake pdf c")
        yield client


@pytest.fixture
def source_with_fakes(data_source):
    """InMemorySource with 3 fake documents."""
    return InMemorySource(
        data_source=data_source,
        documents={
            "docs/a.pdf": b"fake pdf a",
            "docs/b.pdf": b"fake pdf b",
            "docs/c.pdf": b"fake pdf c",
        },
    )


@pytest.fixture
def ledger():
    return InMemoryLedger()


@pytest.fixture
def mock_extractor(monkeypatch):
    """Patch get_extractor to return a simple fake extractor."""

    class FakeExtractor:
        def extract(self, content: bytes) -> str:
            return f"extracted:{content.decode()}"

    monkeypatch.setattr(
        "dia.pipeline.text_extraction.get_extractor",
        lambda ct: FakeExtractor(),
    )


# ---------------------------------------------------------------------------
# Tests: happy path
# ---------------------------------------------------------------------------


def test_processes_all_documents(source_with_fakes, ledger, config, mock_extractor, s3_setup, tmp_path):
    runner = TextExtractionRunner(
        source=source_with_fakes,
        ledger=ledger,
        config=config,
        output_bucket=OUTPUT_BUCKET,
        output_s3_client=s3_setup,
        log_dir=str(tmp_path),
    )
    result = runner.run()

    assert result.total == 3
    assert result.processed == 3
    assert result.failed == 0
    assert result.skipped == 0
    assert result.filtered_out == 0


def test_writes_json_to_output_bucket(source_with_fakes, ledger, config, mock_extractor, s3_setup, tmp_path):
    runner = TextExtractionRunner(
        source=source_with_fakes,
        ledger=ledger,
        config=config,
        output_bucket=OUTPUT_BUCKET,
        output_s3_client=s3_setup,
        log_dir=str(tmp_path),
    )
    runner.run()

    # Check output was written
    response = s3_setup.get_object(Bucket=OUTPUT_BUCKET, Key="test-source/docs/a.pdf.json")
    payload = json.loads(response["Body"].read())

    assert payload["key"] == "docs/a.pdf"
    assert payload["source_name"] == "test-source"
    assert payload["text"] == "extracted:fake pdf a"
    assert payload["chars"] == len("extracted:fake pdf a")
    assert "extracted_at" in payload
    assert "code_version" in payload


# ---------------------------------------------------------------------------
# Tests: local output
# ---------------------------------------------------------------------------


def test_writes_json_to_local_output_dir(source_with_fakes, ledger, config, mock_extractor, tmp_path):
    output_dir = tmp_path / "output"
    runner = TextExtractionRunner(
        source=source_with_fakes,
        ledger=ledger,
        config=config,
        output_dir=output_dir,
        log_dir=str(tmp_path / "logs"),
    )
    result = runner.run()

    assert result.processed == 3

    output_file = output_dir / "test-source" / "docs" / "a.pdf.json"
    assert output_file.exists()

    payload = json.loads(output_file.read_text())
    assert payload["key"] == "docs/a.pdf"
    assert payload["source_name"] == "test-source"
    assert payload["text"] == "extracted:fake pdf a"


def test_output_bucket_and_output_dir_both_set_raises(source_with_fakes, ledger, config, tmp_path):
    with pytest.raises(ValueError, match="exactly one"):
        TextExtractionRunner(
            source=source_with_fakes,
            ledger=ledger,
            config=config,
            output_bucket=OUTPUT_BUCKET,
            output_dir=tmp_path / "output",
            log_dir=str(tmp_path / "logs"),
        )


def test_neither_output_bucket_nor_output_dir_raises(source_with_fakes, ledger, config, tmp_path):
    with pytest.raises(ValueError, match="exactly one"):
        TextExtractionRunner(
            source=source_with_fakes,
            ledger=ledger,
            config=config,
            log_dir=str(tmp_path / "logs"),
        )


def test_updates_ledger(source_with_fakes, ledger, config, mock_extractor, s3_setup, tmp_path):
    runner = TextExtractionRunner(
        source=source_with_fakes,
        ledger=ledger,
        config=config,
        output_bucket=OUTPUT_BUCKET,
        output_s3_client=s3_setup,
        log_dir=str(tmp_path),
    )
    runner.run()

    assert len(ledger.records) == 3
    # All keys should start with "text#"
    assert all(k.startswith("text#") for k in ledger.records)


# ---------------------------------------------------------------------------
# Tests: batching
# ---------------------------------------------------------------------------


def test_processes_in_batches(source_with_fakes, ledger, mock_extractor, s3_setup, tmp_path):
    """With batch_size=2 and 3 docs, should process in 2 batches."""
    config = TextExtractionConfig(batch_size=2)

    runner = TextExtractionRunner(
        source=source_with_fakes,
        ledger=ledger,
        config=config,
        output_bucket=OUTPUT_BUCKET,
        output_s3_client=s3_setup,
        log_dir=str(tmp_path),
    )
    result = runner.run()

    assert result.processed == 3

    # Check log mentions batch progress
    log_files = list(tmp_path.glob("test-source-*.log"))
    log_content = log_files[0].read_text()
    assert "Batch 1/2" in log_content
    assert "Batch 2/2" in log_content


# ---------------------------------------------------------------------------
# Tests: ledger prevents reprocessing
# ---------------------------------------------------------------------------


def test_skips_already_processed(source_with_fakes, ledger, config, mock_extractor, s3_setup, tmp_path):
    # Process once
    runner = TextExtractionRunner(
        source=source_with_fakes,
        ledger=ledger,
        config=config,
        output_bucket=OUTPUT_BUCKET,
        output_s3_client=s3_setup,
        log_dir=str(tmp_path),
    )
    runner.run()

    # Process again — should skip all
    result = runner.run()

    assert result.processed == 0
    assert result.skipped == 3


# ---------------------------------------------------------------------------
# Tests: filters
# ---------------------------------------------------------------------------


def test_filter_reduces_set(ledger, config, mock_extractor, s3_setup, tmp_path):
    data_source = DataSource(
        name="test-source",
        document_type=DocumentType.BUSINESS_CASE,
        bucket=SOURCE_BUCKET,
        prefix="docs/",
    )
    source = InMemorySource(
        data_source=data_source,
        documents={
            "docs/keep.pdf": b"pdf content",
            "docs/skip.docx": b"docx content",
        },
    )

    runner = TextExtractionRunner(
        source=source,
        ledger=ledger,
        config=config,
        output_bucket=OUTPUT_BUCKET,
        output_s3_client=s3_setup,
        filters=[PdfOnlyFilter()],
        log_dir=str(tmp_path),
    )
    result = runner.run()

    assert result.total == 2
    assert result.filtered_out == 1
    assert result.processed == 1


# ---------------------------------------------------------------------------
# Tests: error handling
# ---------------------------------------------------------------------------


def test_failed_doc_does_not_stop_batch(ledger, config, s3_setup, tmp_path):
    """One failing extraction doesn't prevent others from processing."""
    data_source = DataSource(
        name="test-source",
        document_type=DocumentType.BUSINESS_CASE,
        bucket=SOURCE_BUCKET,
        prefix="docs/",
    )
    source = InMemorySource(
        data_source=data_source,
        documents={
            "docs/good.pdf": b"valid content",
            "docs/bad.pdf": b"corrupt",
        },
    )

    call_count = {"n": 0}

    class SometimesFailExtractor:
        def extract(self, content: bytes) -> str:
            call_count["n"] += 1
            if content == b"corrupt":
                msg = "bad PDF"
                raise ValueError(msg)
            return f"extracted:{content.decode()}"

    import dia.pipeline.text_extraction as mod

    original = mod.get_extractor
    mod.get_extractor = lambda ct: SometimesFailExtractor()

    try:
        runner = TextExtractionRunner(
            source=source,
            ledger=ledger,
            config=config,
            output_bucket=OUTPUT_BUCKET,
            output_s3_client=s3_setup,
            log_dir=str(tmp_path),
        )
        result = runner.run()
    finally:
        mod.get_extractor = original

    assert result.processed == 1
    assert result.failed == 1
    assert "docs/bad.pdf" in result.failed_keys
    assert len(ledger.records) == 1


# ---------------------------------------------------------------------------
# Tests: logging
# ---------------------------------------------------------------------------


def test_creates_log_file(source_with_fakes, ledger, config, mock_extractor, s3_setup, tmp_path):
    runner = TextExtractionRunner(
        source=source_with_fakes,
        ledger=ledger,
        config=config,
        output_bucket=OUTPUT_BUCKET,
        output_s3_client=s3_setup,
        log_dir=str(tmp_path),
    )
    runner.run()

    log_files = list(tmp_path.glob("test-source-*.log"))
    assert len(log_files) == 1

    log_content = log_files[0].read_text()
    assert "Starting text extraction" in log_content
    assert "Finished" in log_content
    assert "processed=3" in log_content
