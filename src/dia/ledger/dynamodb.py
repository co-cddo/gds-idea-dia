"""DynamoDB-backed processing ledger for production use."""

from datetime import UTC, datetime
from importlib.metadata import version

import boto3

from dia.ledger.models import LedgerRecord
from dia.types import DocumentReference


def _composite_key(stage: str, source_name: str, ref: DocumentReference) -> str:
    """Build the composite ledger key: stage#source_name#key#version."""
    return f"{stage}#{source_name}#{ref.key}#{ref.version}"


class DynamoDBLedger:
    """DynamoDB-backed processing ledger.

    Stores one item per composite key (stage#source_name#key#version).
    A document is considered processed if its composite key exists in the table.
    """

    def __init__(self, table_name: str, dynamodb_resource=None) -> None:
        self._table_name = table_name
        resource = dynamodb_resource or boto3.resource("dynamodb")
        self._table = resource.Table(table_name)

    def get_unprocessed(self, refs: list[DocumentReference], source_name: str, stage: str) -> list[DocumentReference]:
        """Return refs whose composite key does not exist in the table."""
        if not refs:
            return []

        unprocessed: list[DocumentReference] = []
        for ref in refs:
            key = _composite_key(stage, source_name, ref)
            response = self._table.get_item(
                Key={"document_key": key},
                ProjectionExpression="document_key",
            )
            if "Item" not in response:
                unprocessed.append(ref)

        return unprocessed

    def mark_processed(
        self, ref: DocumentReference, source_name: str, stage: str, department: str | None = None
    ) -> None:
        """Record a document as successfully processed."""
        key = _composite_key(stage, source_name, ref)
        record = LedgerRecord(
            source_name=source_name,
            processed_at=datetime.now(UTC),
            code_version=version("dia"),
            department=department,
        )
        self._table.put_item(
            Item={
                "document_key": key,
                **record.model_dump(mode="json"),
            }
        )

    def list_records(self, source_name: str) -> list[dict]:
        """List all records for a source (across all stages).

        Scans for items whose source_name field matches.
        Fine at our volume (hundreds/low thousands of records).
        """
        from boto3.dynamodb.conditions import Attr

        results = []
        scan_kwargs = {
            "FilterExpression": Attr("source_name").eq(source_name),
        }

        while True:
            response = self._table.scan(**scan_kwargs)
            results.extend(response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                break
            scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

        return results

    def clear(self, source_name: str) -> int:
        """Delete all records for a source (across all stages). Returns count deleted."""
        records = self.list_records(source_name)
        for item in records:
            self._table.delete_item(Key={"document_key": item["document_key"]})
        return len(records)

    def clear_all(self) -> int:
        """Delete all records. Returns count deleted."""
        count = 0
        scan_kwargs: dict = {}

        while True:
            response = self._table.scan(
                ProjectionExpression="document_key",
                **scan_kwargs,
            )
            items = response.get("Items", [])
            for item in items:
                self._table.delete_item(Key={"document_key": item["document_key"]})
                count += 1
            if "LastEvaluatedKey" not in response:
                break
            scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

        return count
