"""In-memory ledger implementation for testing and local development."""

from datetime import UTC, datetime
from importlib.metadata import version

from dia.ledger.keys import composite_key
from dia.ledger.models import LedgerRecord
from dia.types import DocumentReference


class InMemoryLedger:
    """Dict-backed processing ledger for tests and local development.

    Not persistent — state is lost when the process exits.
    """

    def __init__(self) -> None:
        self._records: dict[str, LedgerRecord] = {}

    def get_unprocessed(self, refs: list[DocumentReference], source_name: str, stage: str) -> list[DocumentReference]:
        """Return refs whose composite key is not in the ledger."""
        return [ref for ref in refs if composite_key(stage, source_name, ref) not in self._records]

    def mark_processed(
        self, ref: DocumentReference, source_name: str, stage: str, department: str | None = None
    ) -> None:
        """Record a document as successfully processed."""
        key = composite_key(stage, source_name, ref)
        self._records[key] = LedgerRecord(
            source_name=source_name,
            processed_at=datetime.now(UTC),
            code_version=version("dia"),
            department=department,
        )

    def list_records(self, source_name: str) -> list[dict]:
        """List all records for a source (across all stages).

        Returns a list of dicts with document_key + record fields.
        """
        results = []
        for key, record in self._records.items():
            if record.source_name == source_name:
                results.append({"document_key": key, **record.model_dump(mode="json")})
        return results

    def clear(self, source_name: str) -> int:
        """Delete all records for a source (across all stages). Returns count deleted."""
        keys_to_delete = [k for k, r in self._records.items() if r.source_name == source_name]
        for key in keys_to_delete:
            del self._records[key]
        return len(keys_to_delete)

    def clear_all(self) -> int:
        """Delete all records. Returns count deleted."""
        count = len(self._records)
        self._records.clear()
        return count

    @property
    def records(self) -> dict[str, LedgerRecord]:
        """Access the internal records (useful for test assertions)."""
        return self._records
