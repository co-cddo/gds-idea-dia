"""Tests for dia.ledger — ProcessingLedger implementations."""

from importlib.metadata import version

import boto3
import pytest
from moto import mock_aws

from dia.ledger import DynamoDBLedger, InMemoryLedger
from dia.types import DocumentReference


def _ref(key: str = "docs/file.pdf", version: str = "etag-abc") -> DocumentReference:
    """Helper to create a DocumentReference."""
    return DocumentReference(key=key, content_type="application/pdf", version=version)


# --- InMemoryLedger: get_unprocessed ---


def test_new_refs_are_unprocessed():
    ledger = InMemoryLedger()
    refs = [_ref("a.pdf", "v1"), _ref("b.pdf", "v2")]

    result = ledger.get_unprocessed(refs, "test-source", "text")

    assert result == refs


def test_processed_refs_are_filtered():
    ledger = InMemoryLedger()
    ref = _ref("a.pdf", "v1")
    ledger.mark_processed(ref, "test-source", "text")

    result = ledger.get_unprocessed([ref], "test-source", "text")

    assert result == []


def test_changed_version_is_unprocessed():
    ledger = InMemoryLedger()
    ref_v1 = _ref("a.pdf", "v1")
    ledger.mark_processed(ref_v1, "test-source", "text")

    ref_v2 = _ref("a.pdf", "v2")
    result = ledger.get_unprocessed([ref_v2], "test-source", "text")

    assert result == [ref_v2]


def test_mix_of_processed_and_unprocessed():
    ledger = InMemoryLedger()
    processed = _ref("done.pdf", "v1")
    new = _ref("new.pdf", "v1")
    updated = _ref("updated.pdf", "v2")

    ledger.mark_processed(processed, "source", "text")
    ledger.mark_processed(_ref("updated.pdf", "v1"), "source", "text")

    result = ledger.get_unprocessed([processed, new, updated], "source", "text")

    assert len(result) == 2
    keys = {r.key for r in result}
    assert keys == {"new.pdf", "updated.pdf"}


def test_empty_list_returns_empty():
    ledger = InMemoryLedger()

    result = ledger.get_unprocessed([], "source", "text")

    assert result == []


def test_same_file_different_source_treated_independently():
    """The same filename in two sources should be tracked separately."""
    ledger = InMemoryLedger()
    ref = _ref("files/report.pdf", "v1")

    ledger.mark_processed(ref, "source-a", "text")

    # Same ref but different source — should still be unprocessed
    result = ledger.get_unprocessed([ref], "source-b", "text")

    assert result == [ref]


def test_same_file_different_stage_treated_independently():
    """The same document processed in 'text' stage is still unprocessed for 'graph'."""
    ledger = InMemoryLedger()
    ref = _ref("files/report.pdf", "v1")

    ledger.mark_processed(ref, "source-a", "text")

    # Same ref+source but different stage — should still be unprocessed
    result = ledger.get_unprocessed([ref], "source-a", "graph")

    assert result == [ref]


# --- InMemoryLedger: mark_processed ---


def test_mark_processed_stores_record():
    ledger = InMemoryLedger()
    ref = _ref("a.pdf", "v1")

    ledger.mark_processed(ref, "gats-business-cases", "text")

    key = "text#gats-business-cases#a.pdf#v1"
    record = ledger.records[key]
    assert record.source_name == "gats-business-cases"
    assert record.processed_at is not None
    assert record.code_version == version("dia")
    assert record.department is None


def test_mark_processed_stores_department():
    ledger = InMemoryLedger()
    ref = _ref("a.pdf", "v1")

    ledger.mark_processed(ref, "source", "text", department="HMRC")

    key = "text#source#a.pdf#v1"
    record = ledger.records[key]
    assert record.department == "HMRC"


def test_mark_processed_stores_code_version():
    ledger = InMemoryLedger()
    ref = _ref("a.pdf", "v1")

    ledger.mark_processed(ref, "source", "text")

    key = "text#source#a.pdf#v1"
    record = ledger.records[key]
    # Should be a valid semver-like string
    assert "." in record.code_version


# --- DynamoDBLedger ---

TABLE_NAME = "test-processing-ledger"


@pytest.fixture
def dynamodb_ledger():
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="eu-west-2")
        dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[{"AttributeName": "document_key", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "document_key", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield DynamoDBLedger(table_name=TABLE_NAME, dynamodb_resource=dynamodb)


def test_dynamo_new_refs_are_unprocessed(dynamodb_ledger):
    refs = [_ref("a.pdf", "v1"), _ref("b.pdf", "v2")]

    result = dynamodb_ledger.get_unprocessed(refs, "test-source", "text")

    assert result == refs


def test_dynamo_processed_refs_are_filtered(dynamodb_ledger):
    ref = _ref("a.pdf", "v1")
    dynamodb_ledger.mark_processed(ref, "test-source", "text")

    result = dynamodb_ledger.get_unprocessed([ref], "test-source", "text")

    assert result == []


def test_dynamo_changed_version_is_unprocessed(dynamodb_ledger):
    ref_v1 = _ref("a.pdf", "v1")
    dynamodb_ledger.mark_processed(ref_v1, "test-source", "text")

    ref_v2 = _ref("a.pdf", "v2")
    result = dynamodb_ledger.get_unprocessed([ref_v2], "test-source", "text")

    assert result == [ref_v2]


def test_dynamo_same_file_different_source(dynamodb_ledger):
    ref = _ref("files/report.pdf", "v1")
    dynamodb_ledger.mark_processed(ref, "source-a", "text")

    result = dynamodb_ledger.get_unprocessed([ref], "source-b", "text")

    assert result == [ref]


def test_dynamo_same_file_different_stage(dynamodb_ledger):
    """Text-processed doc is still unprocessed for graph stage."""
    ref = _ref("files/report.pdf", "v1")
    dynamodb_ledger.mark_processed(ref, "source-a", "text")

    result = dynamodb_ledger.get_unprocessed([ref], "source-a", "graph")

    assert result == [ref]


def test_dynamo_empty_list_returns_empty(dynamodb_ledger):
    result = dynamodb_ledger.get_unprocessed([], "source", "text")

    assert result == []


def test_dynamo_stores_code_version(dynamodb_ledger):
    ref = _ref("a.pdf", "v1")
    dynamodb_ledger.mark_processed(ref, "source", "text")

    # Read back the item directly to verify attributes
    table = dynamodb_ledger._table
    response = table.get_item(Key={"document_key": "text#source#a.pdf#v1"})
    item = response["Item"]

    assert item["code_version"] == version("dia")
    assert item["source_name"] == "source"
    assert "processed_at" in item


def test_dynamo_large_batch(dynamodb_ledger):
    """Test that lookups work for >100 items."""
    refs = [_ref(f"file_{i}.pdf", "v1") for i in range(150)]

    result = dynamodb_ledger.get_unprocessed(refs, "source", "text")

    assert len(result) == 150


# --- InMemoryLedger: list_records ---


def test_list_records_returns_matching_source():
    ledger = InMemoryLedger()
    ledger.mark_processed(_ref("a.pdf", "v1"), "source-a", "text")
    ledger.mark_processed(_ref("b.pdf", "v1"), "source-a", "text")
    ledger.mark_processed(_ref("c.pdf", "v1"), "source-b", "text")

    records = ledger.list_records("source-a")

    assert len(records) == 2
    assert all(r["source_name"] == "source-a" for r in records)


def test_list_records_empty_source():
    ledger = InMemoryLedger()
    ledger.mark_processed(_ref("a.pdf", "v1"), "source-a", "text")

    records = ledger.list_records("source-b")

    assert records == []


# --- InMemoryLedger: clear ---


def test_clear_removes_source_records():
    ledger = InMemoryLedger()
    ledger.mark_processed(_ref("a.pdf", "v1"), "source-a", "text")
    ledger.mark_processed(_ref("b.pdf", "v1"), "source-a", "graph")
    ledger.mark_processed(_ref("c.pdf", "v1"), "source-b", "text")

    deleted = ledger.clear("source-a")

    assert deleted == 2
    assert len(ledger.records) == 1
    assert ledger.list_records("source-a") == []
    assert len(ledger.list_records("source-b")) == 1


def test_clear_nonexistent_source_returns_zero():
    ledger = InMemoryLedger()
    ledger.mark_processed(_ref("a.pdf", "v1"), "source-a", "text")

    deleted = ledger.clear("source-b")

    assert deleted == 0
    assert len(ledger.records) == 1


# --- InMemoryLedger: clear_all ---


def test_clear_all_removes_everything():
    ledger = InMemoryLedger()
    ledger.mark_processed(_ref("a.pdf", "v1"), "source-a", "text")
    ledger.mark_processed(_ref("b.pdf", "v1"), "source-b", "graph")

    deleted = ledger.clear_all()

    assert deleted == 2
    assert len(ledger.records) == 0


def test_clear_all_empty_ledger_returns_zero():
    ledger = InMemoryLedger()

    deleted = ledger.clear_all()

    assert deleted == 0


# --- DynamoDBLedger: list_records ---


def test_dynamo_list_records_returns_matching_source(dynamodb_ledger):
    dynamodb_ledger.mark_processed(_ref("a.pdf", "v1"), "source-a", "text")
    dynamodb_ledger.mark_processed(_ref("b.pdf", "v1"), "source-a", "graph")
    dynamodb_ledger.mark_processed(_ref("c.pdf", "v1"), "source-b", "text")

    records = dynamodb_ledger.list_records("source-a")

    assert len(records) == 2
    assert all(r["source_name"] == "source-a" for r in records)


def test_dynamo_list_records_empty_source(dynamodb_ledger):
    dynamodb_ledger.mark_processed(_ref("a.pdf", "v1"), "source-a", "text")

    records = dynamodb_ledger.list_records("source-b")

    assert records == []


# --- DynamoDBLedger: list_all_records ---


def test_dynamo_list_all_records_returns_everything(dynamodb_ledger):
    dynamodb_ledger.mark_processed(_ref("a.pdf", "v1"), "source-a", "text")
    dynamodb_ledger.mark_processed(_ref("b.pdf", "v1"), "source-a", "graph")
    dynamodb_ledger.mark_processed(_ref("c.pdf", "v1"), "source-b", "text")

    records = dynamodb_ledger.list_all_records()

    assert len(records) == 3
    source_names = {r["source_name"] for r in records}
    assert source_names == {"source-a", "source-b"}


def test_dynamo_list_all_records_empty_table(dynamodb_ledger):
    records = dynamodb_ledger.list_all_records()

    assert records == []


# --- DynamoDBLedger: clear ---


def test_dynamo_clear_removes_source_records(dynamodb_ledger):
    dynamodb_ledger.mark_processed(_ref("a.pdf", "v1"), "source-a", "text")
    dynamodb_ledger.mark_processed(_ref("b.pdf", "v1"), "source-a", "graph")
    dynamodb_ledger.mark_processed(_ref("c.pdf", "v1"), "source-b", "text")

    deleted = dynamodb_ledger.clear("source-a")

    assert deleted == 2
    assert dynamodb_ledger.list_records("source-a") == []
    assert len(dynamodb_ledger.list_records("source-b")) == 1


# --- DynamoDBLedger: clear_all ---


def test_dynamo_clear_all_removes_everything(dynamodb_ledger):
    dynamodb_ledger.mark_processed(_ref("a.pdf", "v1"), "source-a", "text")
    dynamodb_ledger.mark_processed(_ref("b.pdf", "v1"), "source-b", "graph")

    deleted = dynamodb_ledger.clear_all()

    assert deleted == 2
    assert dynamodb_ledger.list_records("source-a") == []
    assert dynamodb_ledger.list_records("source-b") == []
