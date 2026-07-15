"""DynamoDB-backed processing ledger for production use."""

from datetime import UTC, datetime
from importlib.metadata import version

import boto3

from dia.ledger.models import LedgerRecord
from dia.types import DocumentReference


def _composite_key(source_name: str, ref: DocumentReference) -> str:
    """Build the composite ledger key."""
    return f"{source_name}#{ref.key}#{ref.version}"


class DynamoDBLedger:
    """DynamoDB-backed processing ledger.

    Stores one item per composite key (source_name#key#version).
    A document is considered processed if its composite key exists in the table.
    """

    def __init__(self, table_name: str, dynamodb_resource=None) -> None:
        self._table_name = table_name
        resource = dynamodb_resource or boto3.resource("dynamodb")
        self._table = resource.Table(table_name)

    def get_unprocessed(self, refs: list[DocumentReference], source_name: str) -> list[DocumentReference]:
        """Return refs whose composite key does not exist in the table."""
        if not refs:
            return []

        unprocessed: list[DocumentReference] = []
        for ref in refs:
            key = _composite_key(source_name, ref)
            response = self._table.get_item(
                Key={"document_key": key},
                ProjectionExpression="document_key",
            )
            if "Item" not in response:
                unprocessed.append(ref)

        return unprocessed

    def mark_processed(self, ref: DocumentReference, source_name: str) -> None:
        """Record a document as successfully processed."""
        key = _composite_key(source_name, ref)
        record = LedgerRecord(
            source_name=source_name,
            processed_at=datetime.now(UTC),
            code_version=version("dia"),
        )
        self._table.put_item(
            Item={
                "document_key": key,
                **record.model_dump(mode="json"),
            }
        )
