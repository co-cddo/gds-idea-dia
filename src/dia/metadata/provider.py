"""A resolved metadata lookup for a source's documents.

MetadataProvider is a simple container — all the complexity of building
the lookup (which CSVs to read, how to parse them, how to explode
multi-file rows) lives in the builder functions in builders.py. This
class just holds the result and provides convenient access.
"""

from dia.metadata.models import DocumentMetadata


class MetadataProvider:
    """Provides metadata for documents in a source, keyed by full document key.

    Used for two purposes:
    - Enrichment: attach metadata to extracted text output
    - Filtering: find which document keys belong to given departments
    """

    def __init__(self, lookup: dict[str, DocumentMetadata]) -> None:
        self._lookup = lookup

    def get_metadata(self, key: str) -> DocumentMetadata | None:
        """Return metadata for a document key, or None if not found."""
        return self._lookup.get(key)

    def files_for(self, departments: list[str]) -> set[str]:
        """Return all document keys belonging to any of the given departments."""
        dept_set = set(departments)
        return {key for key, meta in self._lookup.items() if meta.department in dept_set}

    def departments(self) -> set[str]:
        """Return all known department names in this lookup."""
        return {meta.department for meta in self._lookup.values() if meta.department}

    def __len__(self) -> int:
        return len(self._lookup)
