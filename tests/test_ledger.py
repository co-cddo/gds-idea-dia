"""Tests for dia.ledger — ProcessingLedger implementations."""

from importlib.metadata import version

from dia.ledger import InMemoryLedger
from dia.types import DocumentReference


def _ref(key: str = "docs/file.pdf", version: str = "etag-abc") -> DocumentReference:
    """Helper to create a DocumentReference."""
    return DocumentReference(key=key, content_type="application/pdf", version=version)


# --- InMemoryLedger: get_unprocessed ---


def test_new_refs_are_unprocessed():
    ledger = InMemoryLedger()
    refs = [_ref("a.pdf", "v1"), _ref("b.pdf", "v2")]

    result = ledger.get_unprocessed(refs, "test-source")

    assert result == refs


def test_processed_refs_are_filtered():
    ledger = InMemoryLedger()
    ref = _ref("a.pdf", "v1")
    ledger.mark_processed(ref, "test-source")

    result = ledger.get_unprocessed([ref], "test-source")

    assert result == []


def test_changed_version_is_unprocessed():
    ledger = InMemoryLedger()
    ref_v1 = _ref("a.pdf", "v1")
    ledger.mark_processed(ref_v1, "test-source")

    ref_v2 = _ref("a.pdf", "v2")
    result = ledger.get_unprocessed([ref_v2], "test-source")

    assert result == [ref_v2]


def test_mix_of_processed_and_unprocessed():
    ledger = InMemoryLedger()
    processed = _ref("done.pdf", "v1")
    new = _ref("new.pdf", "v1")
    updated = _ref("updated.pdf", "v2")

    ledger.mark_processed(processed, "source")
    ledger.mark_processed(_ref("updated.pdf", "v1"), "source")

    result = ledger.get_unprocessed([processed, new, updated], "source")

    assert len(result) == 2
    keys = {r.key for r in result}
    assert keys == {"new.pdf", "updated.pdf"}


def test_empty_list_returns_empty():
    ledger = InMemoryLedger()

    result = ledger.get_unprocessed([], "source")

    assert result == []


def test_same_file_different_source_treated_independently():
    """The same filename in two sources should be tracked separately."""
    ledger = InMemoryLedger()
    ref = _ref("files/report.pdf", "v1")

    ledger.mark_processed(ref, "source-a")

    # Same ref but different source — should still be unprocessed
    result = ledger.get_unprocessed([ref], "source-b")

    assert result == [ref]


# --- InMemoryLedger: mark_processed ---


def test_mark_processed_stores_record():
    ledger = InMemoryLedger()
    ref = _ref("a.pdf", "v1")

    ledger.mark_processed(ref, "gats-business-cases")

    key = "gats-business-cases#a.pdf#v1"
    record = ledger.records[key]
    assert record.source_name == "gats-business-cases"
    assert record.processed_at is not None
    assert record.code_version == version("dia")


def test_mark_processed_stores_code_version():
    ledger = InMemoryLedger()
    ref = _ref("a.pdf", "v1")

    ledger.mark_processed(ref, "source")

    key = "source#a.pdf#v1"
    record = ledger.records[key]
    # Should be a valid semver-like string
    assert "." in record.code_version
