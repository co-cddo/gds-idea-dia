"""DynamoDB-backed processing ledger for production use."""

from datetime import UTC, datetime
from importlib.metadata import version

import boto3

from dia.ledger.keys import composite_key
from dia.ledger.models import LedgerRecord
from dia.types import DocumentReference


class DynamoDBLedger:
    """DynamoDB-backed processing ledger.

    Stores one item per composite key (stage#source_name#key#version).
    A document is considered processed if its composite key exists in the table.
    """

    def __init__(self, table_name: str, dynamodb_resource=None) -> None:
        self._table_name = table_name
        self._resource = dynamodb_resource or boto3.resource("dynamodb")
        self._table = self._resource.Table(table_name)

    def get_unprocessed(self, refs: list[DocumentReference], source_name: str, stage: str) -> list[DocumentReference]:
        """Return refs whose composite key does not exist in the table.

        Uses BatchGetItem (up to 100 keys per call) rather than one
        get_item call per ref — cuts API calls by ~100x for large
        document sets (e.g. 10k refs -> ~100 calls instead of 10k).
        """
        if not refs:
            return []

        # Keyed by composite key so we can map found keys back to refs.
        # Preserves ref order (dict insertion order) for non-duplicate keys.
        ref_by_key = {composite_key(stage, source_name, ref): ref for ref in refs}

        found_keys: set[str] = set()
        all_keys = list(ref_by_key.keys())
        for i in range(0, len(all_keys), 100):
            found_keys |= self._batch_get_existing_keys(all_keys[i : i + 100])

        return [ref for key, ref in ref_by_key.items() if key not in found_keys]

    def _batch_get_existing_keys(self, keys: list[str]) -> set[str]:
        """Check which of the given composite keys already exist in the table.

        Retries any UnprocessedKeys returned by DynamoDB (e.g. under
        throttling) until every key in the batch has been resolved.
        """
        found: set[str] = set()
        request_keys = [{"document_key": key} for key in keys]

        while request_keys:
            response = self._resource.batch_get_item(
                RequestItems={
                    self._table_name: {
                        "Keys": request_keys,
                        "ProjectionExpression": "document_key",
                    }
                }
            )
            for item in response.get("Responses", {}).get(self._table_name, []):
                found.add(item["document_key"])

            unprocessed = response.get("UnprocessedKeys", {}).get(self._table_name, {})
            request_keys = unprocessed.get("Keys", [])

        return found

    def mark_processed(
        self, ref: DocumentReference, source_name: str, stage: str, department: str | None = None
    ) -> None:
        """Record a document as successfully processed."""
        key = composite_key(stage, source_name, ref)
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

        return self._scan(FilterExpression=Attr("source_name").eq(source_name))

    def list_all_records(self) -> list[dict]:
        """List every record in the table, across all sources and stages.

        Fine at our volume (hundreds/low thousands of records).
        """
        return self._scan()

    def clear(self, source_name: str) -> int:
        """Delete all records for a source (across all stages). Returns count deleted."""
        records = self.list_records(source_name)
        for item in records:
            self._table.delete_item(Key={"document_key": item["document_key"]})
        return len(records)

    def clear_all(self) -> int:
        """Delete all records. Returns count deleted."""
        items = self._scan(ProjectionExpression="document_key")
        for item in items:
            self._table.delete_item(Key={"document_key": item["document_key"]})
        return len(items)

    def _scan(self, **scan_kwargs) -> list[dict]:
        """Run a full table scan, handling pagination, and return all items.

        DynamoDB scan() only returns up to 1MB per call, so results beyond
        that require following LastEvaluatedKey. This is the one place that
        loop lives — every other method delegates here.
        """
        items: list[dict] = []
        while True:
            response = self._table.scan(**scan_kwargs)
            items.extend(response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                break
            scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        return items
