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

    result = dynamodb_ledger.get_unprocessed(refs, "test-source")

    assert result == refs


def test_dynamo_processed_refs_are_filtered(dynamodb_ledger):
    ref = _ref("a.pdf", "v1")
    dynamodb_ledger.mark_processed(ref, "test-source")

    result = dynamodb_ledger.get_unprocessed([ref], "test-source")

    assert result == []


def test_dynamo_changed_version_is_unprocessed(dynamodb_ledger):
    ref_v1 = _ref("a.pdf", "v1")
    dynamodb_ledger.mark_processed(ref_v1, "test-source")

    ref_v2 = _ref("a.pdf", "v2")
    result = dynamodb_ledger.get_unprocessed([ref_v2], "test-source")

    assert result == [ref_v2]


def test_dynamo_same_file_different_source(dynamodb_ledger):
    ref = _ref("files/report.pdf", "v1")
    dynamodb_ledger.mark_processed(ref, "source-a")

    result = dynamodb_ledger.get_unprocessed([ref], "source-b")

    assert result == [ref]


def test_dynamo_empty_list_returns_empty(dynamodb_ledger):
    result = dynamodb_ledger.get_unprocessed([], "source")

    assert result == []


def test_dynamo_stores_code_version(dynamodb_ledger):
    ref = _ref("a.pdf", "v1")
    dynamodb_ledger.mark_processed(ref, "source")

    # Read back the item directly to verify attributes
    table = dynamodb_ledger._table
    response = table.get_item(Key={"document_key": "source#a.pdf#v1"})
    item = response["Item"]

    assert item["code_version"] == version("dia")
    assert item["source_name"] == "source"
    assert "processed_at" in item


def test_dynamo_large_batch(dynamodb_ledger):
    """Test that lookups work for >100 items."""
    refs = [_ref(f"file_{i}.pdf", "v1") for i in range(150)]

    result = dynamodb_ledger.get_unprocessed(refs, "source")

    assert len(result) == 150
