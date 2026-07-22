"""Integration tests for text extraction — real extractors, no mocks.

Run with:
    uv run pytest tests/test_text_extraction_integration.py -v -m integration

Uses InMemorySource + real PDF/DOCX fixtures + moto S3 for output.
Verifies the full flow: download → extract → write JSON → update ledger.
"""

import json
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from dia.config import TextExtractionConfig
from dia.document_types import DocumentType
from dia.ledger.memory import InMemoryLedger
from dia.pipeline import TextExtractionRunner
from dia.types import DataSource, DocumentReference

FIXTURES = Path(__file__).parent / "fixtures"
OUTPUT_BUCKET = "test-text-extracted"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class InMemorySource:
    """In-memory source backed by real fixture bytes."""

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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def data_source():
    return DataSource(
        name="integration-test",
        document_type=DocumentType.BUSINESS_CASE,
        bucket="source-bucket",
        prefix="docs/",
    )


@pytest.fixture
def pdf_bytes():
    return (FIXTURES / "sample.pdf").read_bytes()


@pytest.fixture
def docx_bytes():
    return (FIXTURES / "sample.docx").read_bytes()


@pytest.fixture
def source_with_real_docs(data_source, pdf_bytes, docx_bytes):
    return InMemorySource(
        data_source=data_source,
        documents={
            "docs/report.pdf": pdf_bytes,
            "docs/notes.docx": docx_bytes,
        },
    )


@pytest.fixture
def output_s3():
    with mock_aws():
        client = boto3.client("s3", region_name="eu-west-2")
        client.create_bucket(
            Bucket=OUTPUT_BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "eu-west-2"},
        )
        yield client


@pytest.fixture
def ledger():
    return InMemoryLedger()


@pytest.fixture
def config():
    return TextExtractionConfig(batch_size=50, max_concurrency=5)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_full_pipeline_extracts_real_documents(source_with_real_docs, ledger, config, output_s3, tmp_path):
    """Real PDF + DOCX extracted end-to-end, JSON written to output bucket."""
    runner = TextExtractionRunner(
        source=source_with_real_docs,
        ledger=ledger,
        config=config,
        output_bucket=OUTPUT_BUCKET,
        output_s3_client=output_s3,
        log_dir=str(tmp_path),
    )
    result = runner.run()

    assert result.total == 2
    assert result.processed == 2
    assert result.failed == 0
    assert result.skipped == 0


@pytest.mark.integration
def test_output_json_contains_extracted_text(source_with_real_docs, ledger, config, output_s3, tmp_path):
    """JSON output contains actual extracted text from the fixtures."""
    runner = TextExtractionRunner(
        source=source_with_real_docs,
        ledger=ledger,
        config=config,
        output_bucket=OUTPUT_BUCKET,
        output_s3_client=output_s3,
        log_dir=str(tmp_path),
    )
    runner.run()

    # Read PDF output
    response = output_s3.get_object(Bucket=OUTPUT_BUCKET, Key="integration-test/docs/report.pdf.json")
    payload = json.loads(response["Body"].read())

    assert payload["key"] == "docs/report.pdf"
    assert payload["source_name"] == "integration-test"
    assert payload["chars"] > 0
    assert "sample document for testing text extraction" in payload["text"]
    assert "extracted_at" in payload
    assert "code_version" in payload


@pytest.mark.integration
def test_ledger_records_with_text_stage(source_with_real_docs, ledger, config, output_s3, tmp_path):
    """Ledger records use the 'text' stage prefix."""
    runner = TextExtractionRunner(
        source=source_with_real_docs,
        ledger=ledger,
        config=config,
        output_bucket=OUTPUT_BUCKET,
        output_s3_client=output_s3,
        log_dir=str(tmp_path),
    )
    runner.run()

    assert len(ledger.records) == 2
    assert all(k.startswith("text#") for k in ledger.records)


@pytest.mark.integration
def test_ledger_prevents_reprocessing(source_with_real_docs, ledger, config, output_s3, tmp_path):
    """Second run skips everything — ledger gate works."""
    runner = TextExtractionRunner(
        source=source_with_real_docs,
        ledger=ledger,
        config=config,
        output_bucket=OUTPUT_BUCKET,
        output_s3_client=output_s3,
        log_dir=str(tmp_path),
    )
    runner.run()

    result = runner.run()

    assert result.processed == 0
    assert result.skipped == 2


@pytest.mark.integration
def test_corrupt_file_fails_gracefully(data_source, pdf_bytes, ledger, config, output_s3, tmp_path):
    """A corrupt file fails but doesn't stop the pipeline."""
    source = InMemorySource(
        data_source=data_source,
        documents={
            "docs/corrupt.pdf": b"this is not a PDF",
            "docs/valid.pdf": pdf_bytes,
        },
    )

    runner = TextExtractionRunner(
        source=source,
        ledger=ledger,
        config=config,
        output_bucket=OUTPUT_BUCKET,
        output_s3_client=output_s3,
        log_dir=str(tmp_path),
    )
    result = runner.run()

    assert result.processed == 1
    assert result.failed == 1
    assert "docs/corrupt.pdf" in result.failed_keys
    assert len(ledger.records) == 1

    # Log contains failure detail
    log_files = list(tmp_path.glob("integration-test-*.log"))
    log_content = log_files[0].read_text()
    assert "Failed" in log_content
    assert "corrupt.pdf" in log_content
