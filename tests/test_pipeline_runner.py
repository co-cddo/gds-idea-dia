"""Tests for dia.pipeline.runner — PipelineRunner and PipelineResult."""

from unittest.mock import patch

import pytest

from dia.filters.noop import NoOpFilter
from dia.ledger.memory import InMemoryLedger
from dia.pipeline import PipelineResult, PipelineRunner
from dia.types import DataSource, DocumentReference, DocumentType

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class InMemorySource:
    """Minimal in-memory document source for testing."""

    def __init__(self, data_source: DataSource, documents: dict[str, bytes]) -> None:
        self._data_source = data_source
        self._documents = documents

    @property
    def data_source(self) -> DataSource:
        return self._data_source

    def list_documents(self) -> list[DocumentReference]:
        refs = []
        for key in sorted(self._documents.keys()):
            ct = "application/pdf" if key.endswith(".pdf") else "application/octet-stream"
            refs.append(DocumentReference(key=key, content_type=ct, version="v1"))
        return refs

    def load_document(self, ref: DocumentReference) -> bytes:
        return self._documents[ref.key]


class HalfFailFilter:
    """Filter that keeps only refs with keys starting with 'keep/'."""

    def filter(self, refs: list[DocumentReference]) -> list[DocumentReference]:
        return [r for r in refs if r.key.startswith("keep/")]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def data_source():
    return DataSource(
        document_type=DocumentType.BUSINESS_CASE,
        bucket="test-bucket",
        prefix="docs/",
    )


@pytest.fixture
def source_with_documents(data_source):
    documents = {
        "docs/report-1.pdf": b"fake pdf 1",
        "docs/report-2.pdf": b"fake pdf 2",
        "docs/report-3.pdf": b"fake pdf 3",
    }
    return InMemorySource(data_source=data_source, documents=documents)


@pytest.fixture
def empty_source(data_source):
    return InMemorySource(data_source=data_source, documents={})


@pytest.fixture
def ledger():
    return InMemoryLedger()


@pytest.fixture
def mock_get_extractor():
    class FakeExtractor:
        def extract(self, content: bytes) -> str:
            return f"extracted: {content.decode()}"

    with patch("dia.pipeline.runner.get_extractor", return_value=FakeExtractor()) as mock:
        yield mock


# ---------------------------------------------------------------------------
# PipelineResult tests
# ---------------------------------------------------------------------------


def test_pipeline_result_is_frozen():
    result = PipelineResult(total=10, processed=5, skipped=3, failed=2)
    with pytest.raises(Exception):
        result.total = 99


def test_pipeline_result_defaults():
    result = PipelineResult(total=0, processed=0, skipped=0, failed=0)
    assert result.failed_keys == []
    assert result.duration_seconds == 0.0
    assert result.filtered_out == 0


# ---------------------------------------------------------------------------
# PipelineRunner — happy path
# ---------------------------------------------------------------------------


def test_processes_all_documents(source_with_documents, ledger, mock_get_extractor, tmp_path):
    runner = PipelineRunner(
        source=source_with_documents,
        ledger=ledger,
        source_name="test-source",
        log_dir=str(tmp_path),
    )
    result = runner.run()

    assert result.total == 3
    assert result.processed == 3
    assert result.skipped == 0
    assert result.failed == 0
    assert result.filtered_out == 0
    assert result.failed_keys == []
    assert result.duration_seconds > 0


def test_skips_already_processed(source_with_documents, ledger, mock_get_extractor, tmp_path):
    refs = source_with_documents.list_documents()
    ledger.mark_processed(refs[0], "test-source")

    runner = PipelineRunner(
        source=source_with_documents,
        ledger=ledger,
        source_name="test-source",
        log_dir=str(tmp_path),
    )
    result = runner.run()

    assert result.total == 3
    assert result.processed == 2
    assert result.skipped == 1
    assert result.failed == 0


def test_empty_source_returns_zero_result(empty_source, ledger, tmp_path):
    runner = PipelineRunner(
        source=empty_source,
        ledger=ledger,
        source_name="test-source",
        log_dir=str(tmp_path),
    )
    result = runner.run()

    assert result.total == 0
    assert result.processed == 0
    assert result.skipped == 0
    assert result.failed == 0


def test_all_skipped_when_ledger_full(source_with_documents, ledger, mock_get_extractor, tmp_path):
    refs = source_with_documents.list_documents()
    for ref in refs:
        ledger.mark_processed(ref, "test-source")

    runner = PipelineRunner(
        source=source_with_documents,
        ledger=ledger,
        source_name="test-source",
        log_dir=str(tmp_path),
    )
    result = runner.run()

    assert result.total == 3
    assert result.processed == 0
    assert result.skipped == 3
    assert result.failed == 0


# ---------------------------------------------------------------------------
# PipelineRunner — filters
# ---------------------------------------------------------------------------


def test_noop_filter_passes_all(source_with_documents, ledger, mock_get_extractor, tmp_path):
    runner = PipelineRunner(
        source=source_with_documents,
        ledger=ledger,
        source_name="test-source",
        filters=[NoOpFilter()],
        log_dir=str(tmp_path),
    )
    result = runner.run()

    assert result.total == 3
    assert result.processed == 3
    assert result.filtered_out == 0


def test_filter_reduces_documents(data_source, ledger, mock_get_extractor, tmp_path):
    documents = {
        "keep/a.pdf": b"content a",
        "keep/b.pdf": b"content b",
        "skip/c.pdf": b"content c",
    }
    source = InMemorySource(data_source=data_source, documents=documents)

    runner = PipelineRunner(
        source=source,
        ledger=ledger,
        source_name="test-source",
        filters=[HalfFailFilter()],
        log_dir=str(tmp_path),
    )
    result = runner.run()

    assert result.total == 3
    assert result.filtered_out == 1
    assert result.processed == 2


# ---------------------------------------------------------------------------
# PipelineRunner — error handling (resilient)
# ---------------------------------------------------------------------------


def test_failed_document_does_not_stop_pipeline(source_with_documents, ledger, tmp_path):
    call_count = {"n": 0}

    class SometimesFailingExtractor:
        def extract(self, content: bytes) -> str:
            call_count["n"] += 1
            if call_count["n"] == 2:
                msg = "corrupt PDF"
                raise ValueError(msg)
            return f"extracted: {content.decode()}"

    with patch("dia.pipeline.runner.get_extractor", return_value=SometimesFailingExtractor()):
        runner = PipelineRunner(
            source=source_with_documents,
            ledger=ledger,
            source_name="test-source",
            log_dir=str(tmp_path),
        )
        result = runner.run()

    assert result.total == 3
    assert result.processed == 2
    assert result.failed == 1
    assert len(result.failed_keys) == 1


def test_failed_document_not_in_ledger(source_with_documents, ledger, tmp_path):
    class AlwaysFailsExtractor:
        def extract(self, content: bytes) -> str:
            msg = "always fails"
            raise ValueError(msg)

    with patch("dia.pipeline.runner.get_extractor", return_value=AlwaysFailsExtractor()):
        runner = PipelineRunner(
            source=source_with_documents,
            ledger=ledger,
            source_name="test-source",
            log_dir=str(tmp_path),
        )
        result = runner.run()

    assert result.failed == 3
    assert result.processed == 0
    assert len(ledger.records) == 0


def test_load_failure_handled_gracefully(data_source, ledger, tmp_path):
    class FailingSource:
        def __init__(self, ds):
            self._data_source = ds

        @property
        def data_source(self):
            return self._data_source

        def list_documents(self):
            return [
                DocumentReference(key="ok.pdf", content_type="application/pdf", version="v1"),
                DocumentReference(key="fail.pdf", content_type="application/pdf", version="v1"),
            ]

        def load_document(self, ref):
            if ref.key == "fail.pdf":
                msg = "S3 access denied"
                raise PermissionError(msg)
            return b"fake content"

    class FakeExtractor:
        def extract(self, content: bytes) -> str:
            return "extracted"

    with patch("dia.pipeline.runner.get_extractor", return_value=FakeExtractor()):
        runner = PipelineRunner(
            source=FailingSource(data_source),
            ledger=ledger,
            source_name="test-source",
            log_dir=str(tmp_path),
        )
        result = runner.run()

    assert result.processed == 1
    assert result.failed == 1
    assert "fail.pdf" in result.failed_keys


# ---------------------------------------------------------------------------
# PipelineRunner — ledger integration
# ---------------------------------------------------------------------------


def test_ledger_records_processed_documents(source_with_documents, ledger, mock_get_extractor, tmp_path):
    runner = PipelineRunner(
        source=source_with_documents,
        ledger=ledger,
        source_name="test-source",
        log_dir=str(tmp_path),
    )
    runner.run()

    assert len(ledger.records) == 3

    # Running again should skip all
    result = runner.run()
    assert result.skipped == 3
    assert result.processed == 0


def test_version_change_triggers_reprocessing(data_source, ledger, mock_get_extractor, tmp_path):
    source = InMemorySource(data_source=data_source, documents={"docs/report.pdf": b"v1"})

    runner = PipelineRunner(
        source=source,
        ledger=ledger,
        source_name="test-source",
        log_dir=str(tmp_path),
    )
    runner.run()

    # A ref with different version should be considered unprocessed
    new_ref = DocumentReference(key="docs/report.pdf", content_type="application/pdf", version="v2")
    unprocessed = ledger.get_unprocessed([new_ref], "test-source")
    assert len(unprocessed) == 1


def test_different_sources_isolated_in_ledger(data_source, ledger, mock_get_extractor, tmp_path):
    source_a = InMemorySource(data_source=data_source, documents={"docs/shared.pdf": b"a"})
    source_b = InMemorySource(data_source=data_source, documents={"docs/shared.pdf": b"b"})

    runner_a = PipelineRunner(source=source_a, ledger=ledger, source_name="source-a", log_dir=str(tmp_path))
    runner_a.run()

    runner_b = PipelineRunner(source=source_b, ledger=ledger, source_name="source-b", log_dir=str(tmp_path))
    result_b = runner_b.run()

    assert result_b.processed == 1


# ---------------------------------------------------------------------------
# PipelineRunner — logging
# ---------------------------------------------------------------------------


def test_creates_log_file(source_with_documents, ledger, mock_get_extractor, tmp_path):
    runner = PipelineRunner(
        source=source_with_documents,
        ledger=ledger,
        source_name="test-source",
        log_dir=str(tmp_path),
    )
    runner.run()

    log_files = list(tmp_path.glob("test-source-*.log"))
    assert len(log_files) == 1


def test_log_file_contains_progress(source_with_documents, ledger, mock_get_extractor, tmp_path):
    runner = PipelineRunner(
        source=source_with_documents,
        ledger=ledger,
        source_name="test-source",
        log_dir=str(tmp_path),
    )
    runner.run()

    log_files = list(tmp_path.glob("test-source-*.log"))
    log_content = log_files[0].read_text()

    assert "Starting extraction" in log_content
    assert "test-source" in log_content
    assert "Finished" in log_content
    assert "processed=3" in log_content


def test_log_file_contains_failure_traceback(source_with_documents, ledger, tmp_path):
    class FailExtractor:
        def extract(self, content: bytes) -> str:
            msg = "bad PDF structure"
            raise ValueError(msg)

    with patch("dia.pipeline.runner.get_extractor", return_value=FailExtractor()):
        runner = PipelineRunner(
            source=source_with_documents,
            ledger=ledger,
            source_name="test-source",
            log_dir=str(tmp_path),
        )
        runner.run()

    log_files = list(tmp_path.glob("test-source-*.log"))
    log_content = log_files[0].read_text()

    assert "Failed" in log_content
    assert "bad PDF structure" in log_content
    assert "Traceback" in log_content
