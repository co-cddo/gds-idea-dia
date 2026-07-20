"""Protocol definition for document sources."""

from typing import Protocol

from dia.types import DataSource, DocumentReference


class DocumentSource(Protocol):
    """Protocol for reading documents from a storage backend.

    Implementations must expose their DataSource (which carries the document type
    and location). The pipeline runner uses source.data_source.document_type to
    derive chunking strategy and entity classifications.
    """

    @property
    def data_source(self) -> DataSource:
        """The data source configuration for this document source."""
        ...

    def list_documents(self) -> list[DocumentReference]:
        """List all available documents without loading content."""
        ...

    def load_document(self, ref: DocumentReference) -> bytes:
        """Load the raw bytes of a document."""
        ...
