"""Protocol definition for the processing ledger."""

from typing import Protocol

from dia.types import DocumentReference


class ProcessingLedger(Protocol):
    """Protocol for tracking which documents have been successfully processed.

    The ledger uses a composite key of stage, source_name, document key, and
    version to determine whether a document needs processing. If any component
    changes, the document is considered unprocessed.

    Stage allows the same ledger table to track multiple pipeline stages
    (e.g. "text" for text extraction, "graph" for graph extraction).

    Failures are not recorded in the ledger — they are handled via logging.
    A failed document will be retried automatically on the next run.
    """

    def get_unprocessed(self, refs: list[DocumentReference], source_name: str, stage: str) -> list[DocumentReference]:
        """Filter refs, returning only those not yet successfully processed.

        A document is considered unprocessed if no record exists for the
        composite key (stage + source_name + key + version).
        """
        ...

    def mark_processed(
        self, ref: DocumentReference, source_name: str, stage: str, department: str | None = None
    ) -> None:
        """Record that a document has been successfully processed."""
        ...
