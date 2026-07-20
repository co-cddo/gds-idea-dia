"""Protocol definition for document filters."""

from typing import Protocol

from dia.types import DocumentReference


class DocumentFilter(Protocol):
    """Protocol for filtering document references before processing.

    Filters are applied between source listing and ledger filtering,
    allowing you to reduce the set of documents that get processed
    (e.g. by department, date range, or sampling).
    """

    def filter(self, refs: list[DocumentReference]) -> list[DocumentReference]:
        """Return only the refs that should be processed.

        Args:
            refs: All document references from the source.

        Returns:
            Subset of refs that pass the filter.
        """
        ...
