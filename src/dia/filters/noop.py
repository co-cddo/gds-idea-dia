"""No-op filter — passes all documents through unchanged."""

from dia.types import DocumentReference


class NoOpFilter:
    """A filter that does nothing — all refs pass through.

    Used as the default when no filtering is configured.
    """

    def filter(self, refs: list[DocumentReference]) -> list[DocumentReference]:
        """Return all refs unchanged."""
        return refs
