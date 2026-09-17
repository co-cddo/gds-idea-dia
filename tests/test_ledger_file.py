"""Tests for dia.ledger.file — JsonFileLedger."""

import json

from dia.ledger.file import JsonFileLedger
from dia.types import DocumentReference


def _ref(key: str = "docs/file.pdf", version: str = "etag-abc") -> DocumentReference:
    """Helper to create a DocumentReference."""
    return DocumentReference(key=key, content_type="application/pdf", version=version)


# ---------------------------------------------------------------------------
# Basic get_unprocessed / mark_processed
# ---------------------------------------------------------------------------


def test_new_refs_are_unprocessed(tmp_path):
    ledger = JsonFileLedger(tmp_path / "ledger.json")
    refs = [_ref("a.pdf", "v1"), _ref("b.pdf", "v2")]

    result = ledger.get_unprocessed(refs, "test-source", "text")

    assert result == refs


def test_processed_refs_are_filtered(tmp_path):
    ledger = JsonFileLedger(tmp_path / "ledger.json")
    ref = _ref("a.pdf", "v1")
    ledger.mark_processed(ref, "test-source", "text")

    result = ledger.get_unprocessed([ref], "test-source", "text")

    assert result == []


def test_changed_version_is_unprocessed(tmp_path):
    ledger = JsonFileLedger(tmp_path / "ledger.json")
    ref_v1 = _ref("a.pdf", "v1")
    ledger.mark_processed(ref_v1, "test-source", "text")

    ref_v2 = _ref("a.pdf", "v2")
    result = ledger.get_unprocessed([ref_v2], "test-source", "text")

    assert result == [ref_v2]


def test_same_file_different_stage_treated_independently(tmp_path):
    ledger = JsonFileLedger(tmp_path / "ledger.json")
    ref = _ref("files/report.pdf", "v1")

    ledger.mark_processed(ref, "source-a", "text")

    result = ledger.get_unprocessed([ref], "source-a", "graph")

    assert result == [ref]


# ---------------------------------------------------------------------------
# mark_processed_many
# ---------------------------------------------------------------------------


def test_mark_processed_many_stores_all_records(tmp_path):
    ledger = JsonFileLedger(tmp_path / "ledger.json")
    refs = [_ref("a.pdf", "v1"), _ref("b.pdf", "v1"), _ref("c.pdf", "v1")]

    ledger.mark_processed_many([(ref, None) for ref in refs], "source", "text")

    result = ledger.get_unprocessed(refs, "source", "text")
    assert result == []


def test_mark_processed_many_stores_per_entry_department(tmp_path):
    ledger = JsonFileLedger(tmp_path / "ledger.json")
    ref_a = _ref("a.pdf", "v1")
    ref_b = _ref("b.pdf", "v1")

    ledger.mark_processed_many([(ref_a, "Home Office"), (ref_b, "Cabinet Office")], "source", "text")

    records = {r["document_key"]: r for r in ledger.list_records("source")}
    assert records["text#source#a.pdf#v1"]["department"] == "Home Office"
    assert records["text#source#b.pdf#v1"]["department"] == "Cabinet Office"


def test_mark_processed_many_empty_list_is_noop(tmp_path):
    path = tmp_path / "ledger.json"
    ledger = JsonFileLedger(path)

    ledger.mark_processed_many([], "source", "text")

    assert ledger.record_count == 0
    assert not path.exists()  # no write happened at all


def test_mark_processed_many_writes_file_once(tmp_path, monkeypatch):
    """The whole point of mark_processed_many is a single disk write,
    not one write per entry."""
    ledger = JsonFileLedger(tmp_path / "ledger.json")
    save_calls = 0
    original_save = ledger._save

    def _counting_save():
        nonlocal save_calls
        save_calls += 1
        original_save()

    monkeypatch.setattr(ledger, "_save", _counting_save)
    refs = [_ref(f"file_{i}.pdf", "v1") for i in range(10)]

    ledger.mark_processed_many([(ref, None) for ref in refs], "source", "text")

    assert save_calls == 1


def test_mark_processed_many_persists_to_disk(tmp_path):
    path = tmp_path / "ledger.json"
    ledger = JsonFileLedger(path)
    refs = [_ref("a.pdf", "v1"), _ref("b.pdf", "v1")]

    ledger.mark_processed_many([(ref, None) for ref in refs], "source", "text")

    ledger2 = JsonFileLedger(path)
    assert ledger2.get_unprocessed(refs, "source", "text") == []


# ---------------------------------------------------------------------------
# File persistence
# ---------------------------------------------------------------------------


def test_creates_file_on_first_write(tmp_path):
    path = tmp_path / "ledger.json"
    assert not path.exists()

    ledger = JsonFileLedger(path)
    ledger.mark_processed(_ref("a.pdf", "v1"), "source", "text")

    assert path.exists()


def test_file_contains_valid_json(tmp_path):
    path = tmp_path / "ledger.json"
    ledger = JsonFileLedger(path)
    ledger.mark_processed(_ref("a.pdf", "v1"), "source", "text")

    data = json.loads(path.read_text())

    assert "text#source#a.pdf#v1" in data
    assert data["text#source#a.pdf#v1"]["source_name"] == "source"


def test_creates_parent_directories(tmp_path):
    path = tmp_path / "nested" / "dir" / "ledger.json"
    ledger = JsonFileLedger(path)
    ledger.mark_processed(_ref("a.pdf", "v1"), "source", "text")

    assert path.exists()


def test_loads_existing_file_on_init(tmp_path):
    path = tmp_path / "ledger.json"

    # First instance writes a record
    ledger1 = JsonFileLedger(path)
    ledger1.mark_processed(_ref("a.pdf", "v1"), "source", "text")

    # Second instance should see it (resumability across process restarts)
    ledger2 = JsonFileLedger(path)
    result = ledger2.get_unprocessed([_ref("a.pdf", "v1")], "source", "text")

    assert result == []


def test_missing_file_starts_empty(tmp_path):
    path = tmp_path / "does-not-exist.json"
    ledger = JsonFileLedger(path)

    assert ledger.record_count == 0


def test_empty_file_starts_empty(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text("")

    ledger = JsonFileLedger(path)

    assert ledger.record_count == 0


def test_corrupt_file_starts_empty(tmp_path):
    path = tmp_path / "corrupt.json"
    path.write_text("{not valid json")

    ledger = JsonFileLedger(path)

    assert ledger.record_count == 0


# ---------------------------------------------------------------------------
# list_records
# ---------------------------------------------------------------------------


def test_list_records_returns_matching_source(tmp_path):
    ledger = JsonFileLedger(tmp_path / "ledger.json")
    ledger.mark_processed(_ref("a.pdf", "v1"), "source-a", "text")
    ledger.mark_processed(_ref("b.pdf", "v1"), "source-a", "graph")
    ledger.mark_processed(_ref("c.pdf", "v1"), "source-b", "text")

    records = ledger.list_records("source-a")

    assert len(records) == 2
    assert all(r["source_name"] == "source-a" for r in records)


def test_list_records_empty_source(tmp_path):
    ledger = JsonFileLedger(tmp_path / "ledger.json")
    ledger.mark_processed(_ref("a.pdf", "v1"), "source-a", "text")

    records = ledger.list_records("source-b")

    assert records == []


# ---------------------------------------------------------------------------
# clear / clear_all
# ---------------------------------------------------------------------------


def test_clear_removes_source_records(tmp_path):
    ledger = JsonFileLedger(tmp_path / "ledger.json")
    ledger.mark_processed(_ref("a.pdf", "v1"), "source-a", "text")
    ledger.mark_processed(_ref("b.pdf", "v1"), "source-a", "graph")
    ledger.mark_processed(_ref("c.pdf", "v1"), "source-b", "text")

    deleted = ledger.clear("source-a")

    assert deleted == 2
    assert ledger.record_count == 1
    assert ledger.list_records("source-a") == []


def test_clear_nonexistent_source_returns_zero(tmp_path):
    ledger = JsonFileLedger(tmp_path / "ledger.json")
    ledger.mark_processed(_ref("a.pdf", "v1"), "source-a", "text")

    deleted = ledger.clear("source-b")

    assert deleted == 0
    assert ledger.record_count == 1


def test_clear_all_removes_everything(tmp_path):
    ledger = JsonFileLedger(tmp_path / "ledger.json")
    ledger.mark_processed(_ref("a.pdf", "v1"), "source-a", "text")
    ledger.mark_processed(_ref("b.pdf", "v1"), "source-b", "graph")

    deleted = ledger.clear_all()

    assert deleted == 2
    assert ledger.record_count == 0


def test_clear_persists_to_disk(tmp_path):
    path = tmp_path / "ledger.json"
    ledger = JsonFileLedger(path)
    ledger.mark_processed(_ref("a.pdf", "v1"), "source-a", "text")
    ledger.clear("source-a")

    # Reload from disk to confirm persistence
    ledger2 = JsonFileLedger(path)
    assert ledger2.record_count == 0
