"""Data model for document metadata resolved from source metadata systems."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentMetadata:
    """Metadata associated with a document, resolved from its source's
    metadata system (historic CSV, GATS export, or folder structure).

    All fields are optional — which ones get populated depends on the
    source and what metadata it actually has available. `department` is
    the only field expected to be populated across all sources.
    """

    department: str | None = None
    alb: str | None = None
    spend_id: str | None = None
    project_name: str | None = None
    assurance_date: str | None = None
