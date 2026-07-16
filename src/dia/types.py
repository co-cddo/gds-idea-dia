"""Shared type definitions for DIA."""

from dataclasses import dataclass

from dia.document_types import DocumentType

__all__ = ["DataSource", "DocumentReference", "DocumentType"]


@dataclass(frozen=True)
class DataSource:
    """A location where documents of a specific type can be found."""

    document_type: DocumentType
    bucket: str
    prefix: str = ""
    file_extensions: tuple[str, ...] = (".pdf", ".docx")
    cross_account: bool = False


@dataclass(frozen=True)
class DocumentReference:
    """A lightweight reference to a document (no content loaded).

    The version field is an opaque change-detection signal provided by the
    source (e.g. S3 ETag, file mtime+size). The ledger uses it to detect
    when a file at the same key has been updated.
    """

    key: str
    content_type: str
    version: str
