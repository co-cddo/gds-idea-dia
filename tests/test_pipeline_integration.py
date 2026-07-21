"""Integration tests for the full pipeline — no mocks, real extractors.

These tests exercise the complete pipeline flow end-to-end using real
PDF/DOCX fixtures and real extractors. They verify that sources, filters,
the ledger, extractors, and the pipeline runner all integrate correctly.

Run with:
    uv run pytest tests/test_pipeline_integration.py -v

Or just the integration-marked tests across the suite:
    uv run pytest -m integration -v

These tests use InMemorySource and InMemoryLedger (no AWS calls) but
real PdfExtractor/DocxExtractor against actual fixture files.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from dia.cli import app
from dia.ledger.memory import InMemoryLedger
from dia.pipeline import PipelineRunner
from dia.types import DataSource, DocumentReference, DocumentType

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class InMemorySource:
    """In-memory document source for integration tests."""

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
    """Filter that only allows PDF files through. Used to test filter behaviour."""

    def filter(self, refs: list[DocumentReference]) -> list[DocumentReference]:
        return [r for r in refs if r.key.lower().endswith(".pdf")]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def data_source():
    return DataSource(
        document_type=DocumentType.BUSINESS_CASE,
        bucket="integration-test-bucket",
        prefix="docs/",
    )


@pytest.fixture
def pdf_bytes():
    return (FIXTURES / "sample.pdf").read_bytes()


@pytest.fixture
def docx_bytes():
    return (FIXTURES / "sample.docx").read_bytes()


@pytest.fixture
def source_with_both(data_source, pdf_bytes, docx_bytes):
    """Source with one PDF and one DOCX — both real, extractable files."""
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


# ---------------------------------------------------------------------------
# Test 1: Full pipeline processes real documents (no mocks)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_full_pipeline_processes_real_documents(source_with_both, ledger, tmp_path):
    """The pipeline extracts text from real PDF and DOCX files without mocks."""
    runner = PipelineRunner(
        source=source_with_both,
        ledger=ledger,
        source_name="integration-test",
        log_dir=str(tmp_path),
    )
    result = runner.run()

    # All documents processed successfully
    assert result.total == 2
    assert result.processed == 2
    assert result.failed == 0
    assert result.skipped == 0
    assert result.filtered_out == 0

    # Ledger recorded both successes
    assert len(ledger.records) == 2


# ---------------------------------------------------------------------------
# Test 2: Ledger prevents reprocessing
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_ledger_prevents_reprocessing(source_with_both, ledger, tmp_path):
    """Running twice with the same ledger skips already-processed documents."""
    runner = PipelineRunner(
        source=source_with_both,
        ledger=ledger,
        source_name="integration-test",
        log_dir=str(tmp_path),
    )

    # First run: processes everything
    first_result = runner.run()
    assert first_result.processed == 2
    assert len(ledger.records) == 2

    # Second run: skips everything (ledger gate works)
    second_result = runner.run()
    assert second_result.processed == 0
    assert second_result.skipped == 2

    # Ledger unchanged — no duplicates
    assert len(ledger.records) == 2


# ---------------------------------------------------------------------------
# Test 3: Filter reduces the processing set
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_filter_reduces_processing_set(source_with_both, ledger, tmp_path):
    """A PdfOnlyFilter removes the DOCX before processing begins."""
    runner = PipelineRunner(
        source=source_with_both,
        ledger=ledger,
        source_name="integration-test",
        filters=[PdfOnlyFilter()],
        log_dir=str(tmp_path),
    )
    result = runner.run()

    # Filter removed the DOCX
    assert result.total == 2
    assert result.filtered_out == 1

    # Only the PDF was processed
    assert result.processed == 1
    assert result.failed == 0

    # Ledger only has the PDF
    assert len(ledger.records) == 1


# ---------------------------------------------------------------------------
# Test 4: Filter and ledger interact correctly
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_filter_and_ledger_interact_correctly(source_with_both, ledger, tmp_path):
    """Filters run BEFORE the ledger check. Both mechanisms work together."""
    # First run: no filter, processes both
    runner_no_filter = PipelineRunner(
        source=source_with_both,
        ledger=ledger,
        source_name="integration-test",
        log_dir=str(tmp_path),
    )
    first_result = runner_no_filter.run()
    assert first_result.processed == 2
    assert len(ledger.records) == 2

    # Second run: with PdfOnlyFilter
    # The DOCX is filtered out, the PDF is already in ledger → skipped
    runner_with_filter = PipelineRunner(
        source=source_with_both,
        ledger=ledger,
        source_name="integration-test",
        filters=[PdfOnlyFilter()],
        log_dir=str(tmp_path),
    )
    second_result = runner_with_filter.run()

    # Filter removes DOCX from consideration
    assert second_result.filtered_out == 1

    # PDF passes filter but is already in ledger → skipped
    assert second_result.skipped == 1
    assert second_result.processed == 0


# ---------------------------------------------------------------------------
# Test 5: Log file captures the full run
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_log_file_captures_full_run(source_with_both, ledger, tmp_path):
    """The log file contains detailed progress at DEBUG level."""
    runner = PipelineRunner(
        source=source_with_both,
        ledger=ledger,
        source_name="integration-test",
        log_dir=str(tmp_path),
    )
    runner.run()

    log_files = list(tmp_path.glob("integration-test-*.log"))
    assert len(log_files) == 1

    log_content = log_files[0].read_text()

    # Key progress markers present
    assert "Starting extraction" in log_content
    assert "integration-test" in log_content
    assert "Discovered 2 documents" in log_content
    assert "Extracted: chars=" in log_content
    assert "Finished: processed=2" in log_content

    # No failures
    assert "Failed:" not in log_content

    # DEBUG-level detail present (file handler captures these)
    assert "Text preview:" in log_content
    assert "Downloaded:" in log_content


# ---------------------------------------------------------------------------
# Test 6: Failures logged with full traceback
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_failure_logged_with_traceback(data_source, pdf_bytes, ledger, tmp_path):
    """A corrupt file fails gracefully and the traceback appears in the log."""
    source = InMemorySource(
        data_source=data_source,
        documents={
            "docs/corrupt.pdf": b"this is not a real PDF file",
            "docs/valid.pdf": pdf_bytes,
        },
    )

    runner = PipelineRunner(
        source=source,
        ledger=ledger,
        source_name="integration-test",
        log_dir=str(tmp_path),
    )
    result = runner.run()

    # One succeeds, one fails
    assert result.processed == 1
    assert result.failed == 1
    assert "docs/corrupt.pdf" in result.failed_keys

    # Ledger only records the success
    assert len(ledger.records) == 1

    # Log file contains the failure detail
    log_files = list(tmp_path.glob("integration-test-*.log"))
    log_content = log_files[0].read_text()

    assert "Failed" in log_content
    assert "corrupt.pdf" in log_content
    assert "Traceback" in log_content


# ---------------------------------------------------------------------------
# Test 7: CLI end-to-end with real extractors
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_cli_extract_end_to_end(data_source, pdf_bytes, docx_bytes, tmp_path):
    """The dia extract CLI command works end-to-end with real extractors."""
    source = InMemorySource(
        data_source=data_source,
        documents={
            "docs/report.pdf": pdf_bytes,
            "docs/notes.docx": docx_bytes,
        },
    )

    cli_runner = CliRunner()

    with (
        patch("dia.sources.known.get_source", return_value=data_source),
        patch("dia.sources.s3.S3DocumentSource", return_value=source),
    ):
        result = cli_runner.invoke(app, ["extract", "--source", "integration-test", "--log-dir", str(tmp_path)])

    # CLI exits successfully
    assert result.exit_code == 0, f"CLI failed with output:\n{result.output}"

    # Output shows correct summary
    assert "Processed:        2" in result.output
    assert "Failed:           0" in result.output

    # Log file was created
    log_files = list(tmp_path.glob("integration-test-*.log"))
    assert len(log_files) == 1
