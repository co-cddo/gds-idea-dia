"""Protocol definition for document sources."""

from typing import Protocol

from dia.types import DocumentReference


class DocumentSource(Protocol):
    """Protocol for reading documents from a storage backend."""

    def list_documents(self) -> list[DocumentReference]:
        """List all available documents without loading content."""
        ...

    def load_document(self, ref: DocumentReference) -> bytes:
        """Load the raw bytes of a document."""
        ...
