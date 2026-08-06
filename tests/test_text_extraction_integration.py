"""Integration tests for text extraction — real extractors, no mocks.

Run with:
    uv run pytest tests/test_text_extraction_integration.py -v -m integration

Uses InMemorySource + real PDF/DOCX fixtures + InMemoryWriter for output.
Verifies the full flow: download → extract → write → update ledger,
including metadata-driven filtering and enrichment.
"""

from pathlib import Path

import pytest

from dia.config import TextExtractionConfig
from dia.document_types import DocumentType
from dia.ledger.memory import InMemoryLedger
from dia.metadata.filter import MetadataDepartmentFilter
from dia.metadata.models import DocumentMetadata
from dia.metadata.provider import MetadataProvider
from dia.pipeline import TextExtractionRunner
from dia.types import DataSource, DocumentReference
from dia.writers.memory import InMemoryWriter

FIXTURES = Path(__file__).parent / "fixtures"


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
def ledger():
    return InMemoryLedger()


@pytest.fixture
def writer():
    return InMemoryWriter()


@pytest.fixture
def config():
    return TextExtractionConfig(batch_size=50, max_concurrency=5)


# ---------------------------------------------------------------------------
# Tests: real extraction, no mocks
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_full_pipeline_extracts_real_documents(source_with_real_docs, ledger, config, writer, tmp_path):
    """Real PDF + DOCX extracted end-to-end, written via the InMemoryWriter."""
    runner = TextExtractionRunner(
        source=source_with_real_docs,
        ledger=ledger,
        config=config,
        writer=writer,
        log_dir=str(tmp_path),
    )
    result = runner.run()

    assert result.total == 2
    assert result.processed == 2
    assert result.failed == 0
    assert result.skipped == 0


@pytest.mark.integration
def test_output_contains_extracted_text(source_with_real_docs, ledger, config, writer, tmp_path):
    """Output contains actual extracted text from the fixtures."""
    runner = TextExtractionRunner(
        source=source_with_real_docs,
        ledger=ledger,
        config=config,
        writer=writer,
        log_dir=str(tmp_path),
    )
    runner.run()

    payload = writer.written["integration-test/docs/report.pdf.json"]

    assert payload["key"] == "docs/report.pdf"
    assert payload["source_name"] == "integration-test"
    assert payload["chars"] > 0
    assert "sample document for testing text extraction" in payload["text"]
    assert "extracted_at" in payload
    assert "code_version" in payload


@pytest.mark.integration
def test_ledger_records_with_text_stage(source_with_real_docs, ledger, config, writer, tmp_path):
    """Ledger records use the 'text' stage prefix."""
    runner = TextExtractionRunner(
        source=source_with_real_docs,
        ledger=ledger,
        config=config,
        writer=writer,
        log_dir=str(tmp_path),
    )
    runner.run()

    assert len(ledger.records) == 2
    assert all(k.startswith("text#") for k in ledger.records)


@pytest.mark.integration
def test_ledger_prevents_reprocessing(source_with_real_docs, ledger, config, writer, tmp_path):
    """Second run skips everything — ledger gate works."""
    runner = TextExtractionRunner(
        source=source_with_real_docs,
        ledger=ledger,
        config=config,
        writer=writer,
        log_dir=str(tmp_path),
    )
    runner.run()

    result = runner.run()

    assert result.processed == 0
    assert result.skipped == 2


@pytest.mark.integration
def test_corrupt_file_fails_gracefully(data_source, pdf_bytes, ledger, config, writer, tmp_path):
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
        writer=writer,
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


# ---------------------------------------------------------------------------
# Metadata: department filtering + enrichment, end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_metadata_filters_and_enriches_real_documents(
    data_source, pdf_bytes, docx_bytes, ledger, config, writer, tmp_path
):
    """One metadata lookup drives both department filtering AND enrichment.

    docs/report.pdf belongs to Home Office (included).
    docs/notes.docx belongs to HMRC (filtered out — we only want Home Office).
    """
    source = InMemorySource(
        data_source=data_source,
        documents={
            "docs/report.pdf": pdf_bytes,
            "docs/notes.docx": docx_bytes,
        },
    )

    metadata = MetadataProvider(
        {
            "docs/report.pdf": DocumentMetadata(
                department="Home Office",
                alb="National Crime Agency",
                spend_id="CS-100",
                project_name="Project Alpha",
            ),
            "docs/notes.docx": DocumentMetadata(department="HMRC"),
        }
    )
    dept_filter = MetadataDepartmentFilter(metadata, ["Home Office"])

    runner = TextExtractionRunner(
        source=source,
        ledger=ledger,
        config=config,
        writer=writer,
        filters=[dept_filter],
        metadata=metadata,
        log_dir=str(tmp_path),
    )
    result = runner.run()

    # Filtering: only report.pdf (Home Office) passes
    assert result.total == 2
    assert result.filtered_out == 1
    assert result.processed == 1

    # Enrichment: the processed document carries its metadata
    payload = writer.written["integration-test/docs/report.pdf.json"]

    assert "sample document for testing text extraction" in payload["text"]
    assert payload["metadata"]["department"] == "Home Office"
    assert payload["metadata"]["alb"] == "National Crime Agency"
    assert payload["metadata"]["spend_id"] == "CS-100"
    assert payload["metadata"]["project_name"] == "Project Alpha"

    # The HMRC document was never downloaded, extracted, or written
    assert "integration-test/docs/notes.docx.json" not in writer.written
