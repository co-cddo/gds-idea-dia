"""Bridges a MetadataProvider into the DocumentFilter protocol.

This is the department-filtering mechanism now that metadata is resolved
once and shared between filtering and enrichment — it replaces the
standalone SpendID-prefix-matching DepartmentFilter, since the metadata
provider's lookup already has the exact document keys per department
(no prefix guessing needed).
"""

from dia.metadata.provider import MetadataProvider
from dia.types import DocumentReference


class MetadataDepartmentFilter:
    """Filters documents to those belonging to specific departments.

    Uses a MetadataProvider's resolved lookup rather than independently
    re-deriving department membership — filtering and enrichment share
    the exact same metadata resolution.
    """

    def __init__(self, metadata: MetadataProvider, departments: list[str]) -> None:
        self._target_keys = metadata.files_for(departments)

    def filter(self, refs: list[DocumentReference]) -> list[DocumentReference]:
        """Return only the refs whose key belongs to the configured departments."""
        return [ref for ref in refs if ref.key in self._target_keys]
