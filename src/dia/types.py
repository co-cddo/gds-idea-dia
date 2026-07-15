"""Shared type definitions for DIA."""

from dataclasses import dataclass
from enum import StrEnum


class DocumentType(StrEnum):
    """Document types supported by the extraction pipeline."""

    BUSINESS_CASE = "business_case"
    SR_BIDS = "sr_bids"
    CONTRACT_FINDER = "contract_finder"


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
    """A lightweight reference to a document in S3 (no content loaded)."""

    key: str
    content_type: str
