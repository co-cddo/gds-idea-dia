"""JSON file-backed ledger for local development.

Persists processing state to a local JSON file. Useful for running the
pipeline locally without DynamoDB — state survives across runs so you
can resume where you left off.
"""

import json
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from dia.ledger.keys import composite_key
from dia.ledger.models import LedgerRecord
from dia.types import DocumentReference


class JsonFileLedger:
    """JSON file-backed processing ledger for local development.

    Reads the entire ledger into memory on init, writes back to disk
    on every mark_processed call. Simple and safe for single-process CLI use.

    The file is created if it doesn't exist.
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._records: dict[str, dict] = self._load()

    def get_unprocessed(self, refs: list[DocumentReference], source_name: str, stage: str) -> list[DocumentReference]:
        """Return refs whose composite key is not in the ledger."""
        return [ref for ref in refs if composite_key(stage, source_name, ref) not in self._records]

    def mark_processed(
        self, ref: DocumentReference, source_name: str, stage: str, department: str | None = None
    ) -> None:
        """Record a document as successfully processed and persist to disk."""
        key = composite_key(stage, source_name, ref)
        record = LedgerRecord(
            source_name=source_name,
            processed_at=datetime.now(UTC),
            code_version=version("dia"),
            department=department,
        )
        self._records[key] = record.model_dump(mode="json")
        self._save()

    def list_records(self, source_name: str) -> list[dict]:
        """List all records for a source (across all stages)."""
        return [
            {"document_key": key, **record}
            for key, record in self._records.items()
            if record.get("source_name") == source_name
        ]

    def clear(self, source_name: str) -> int:
        """Delete all records for a source. Returns count deleted."""
        keys_to_delete = [k for k, r in self._records.items() if r.get("source_name") == source_name]
        for key in keys_to_delete:
            del self._records[key]
        self._save()
        return len(keys_to_delete)

    def clear_all(self) -> int:
        """Delete all records. Returns count deleted."""
        count = len(self._records)
        self._records.clear()
        self._save()
        return count

    @property
    def record_count(self) -> int:
        """Number of records in the ledger."""
        return len(self._records)

    def _load(self) -> dict[str, dict]:
        """Load records from disk. Returns empty dict if file doesn't exist."""
        if not self._path.exists():
            return {}
        try:
            content = self._path.read_text(encoding="utf-8")
            return json.loads(content) if content.strip() else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self) -> None:
        """Write records to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._records, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
