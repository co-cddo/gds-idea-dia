"""In-memory ledger implementation for testing and local development."""

from datetime import UTC, datetime
from importlib.metadata import version

from dia.ledger.models import LedgerRecord
from dia.types import DocumentReference


def _composite_key(source_name: str, ref: DocumentReference) -> str:
    """Build the composite ledger key."""
    return f"{source_name}#{ref.key}#{ref.version}"


class InMemoryLedger:
    """Dict-backed processing ledger for tests and local development.

    Not persistent — state is lost when the process exits.
    """

    def __init__(self) -> None:
        self._records: dict[str, LedgerRecord] = {}

    def get_unprocessed(self, refs: list[DocumentReference], source_name: str) -> list[DocumentReference]:
        """Return refs whose composite key is not in the ledger."""
        return [ref for ref in refs if _composite_key(source_name, ref) not in self._records]

    def mark_processed(self, ref: DocumentReference, source_name: str) -> None:
        """Record a document as successfully processed."""
        key = _composite_key(source_name, ref)
        self._records[key] = LedgerRecord(
            source_name=source_name,
            processed_at=datetime.now(UTC),
            code_version=version("dia"),
        )

    @property
    def records(self) -> dict[str, LedgerRecord]:
        """Access the internal records (useful for test assertions)."""
        return self._records
