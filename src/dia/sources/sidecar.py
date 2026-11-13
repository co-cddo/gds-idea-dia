"""The metadata sidecar written next to every document.

A sidecar is a small JSON file in Bedrock's format, stored beside its document:

    files/case-123.pdf
    files/case-123.pdf.metadata.json

    {"metadataAttributes": {"document_type": "business_case", "date": "2025"}}

The knowledge bases read it as it is (the values are stored for filtering and are not
embedded), and the graph's text stage reads it to add the same fields to the extracted
text. Both go through this module, so they cannot disagree about the format.

`Sidecar` holds the fields. `check` compares a sidecar with the keys its source
declares in `dia.sources.definitions`.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, StrictBool, StrictStr, ValidationError

from dia.document_types import DocumentType
from dia.sources.models import SourceDefinition

SIDECAR_SUFFIX = ".metadata.json"
_WRAPPER_KEY = "metadataAttributes"


class SidecarError(ValueError):
    """A sidecar is malformed, or does not match its source."""


class Sidecar(BaseModel, frozen=True, extra="forbid"):
    """The metadata for one document. Only `document_type` is always known.

    Field names are the metadata keys the knowledge bases filter on. A source declares
    which of them its documents may carry (`SourceDefinition.metadata_keys`).

    Attributes:
        document_type: What kind of document it is. Matches the agent's filters.
        department_name: The department the document belongs to.
        alb: The arm's-length body, where there is one.
        report_type: The kind of report, for sources that have several.
        spend_id: The spend control case ID (GATS and SR bids).
        project_name: The project the document belongs to.
        file_reference: The document's ID in the ledger of source files.
        date: The document's own date, as text in whatever precision is known: `2025` when only
            the year is known, `202606` for a month, `20260901` for a day.
        is_latest: Whether it is the newest DBR document for its department.
    """

    document_type: DocumentType
    department_name: StrictStr | None = None
    alb: StrictStr | None = None
    report_type: StrictStr | None = None
    spend_id: StrictStr | None = None
    project_name: StrictStr | None = None
    file_reference: StrictStr | None = None
    date: StrictStr | None = None
    is_latest: StrictBool | None = None


def sidecar_key(document_key: str) -> str:
    """The S3 key of the sidecar for a document.

    Args:
        document_key: The document's key, for example `files/case-123.pdf`.

    Returns:
        The key beside it, for example `files/case-123.pdf.metadata.json`.

    Raises:
        SidecarError: If the key is empty or is already a sidecar's.
    """
    if not document_key:
        raise SidecarError("a document key cannot be empty")
    if document_key.endswith(SIDECAR_SUFFIX):
        raise SidecarError(f"{document_key!r} is already a sidecar key")
    return f"{document_key}{SIDECAR_SUFFIX}"


def to_json(sidecar: Sidecar) -> str:
    """Write a sidecar in Bedrock's format, leaving out the fields that are not set.

    Args:
        sidecar: The metadata to write.

    Returns:
        The JSON text for the sidecar file.
    """
    attributes = sidecar.model_dump(mode="json", exclude_none=True)
    return json.dumps({_WRAPPER_KEY: attributes}, indent=2)


def from_json(text: str) -> Sidecar:
    """Read a sidecar written in Bedrock's simple format.

    Args:
        text: The JSON text of a sidecar file.

    Returns:
        The metadata it holds.

    Raises:
        SidecarError: If the text is not JSON, is not in the expected shape, has a key
            we do not know, or has a value of the wrong type.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise SidecarError(f"sidecar is not valid JSON: {error}") from error

    if not isinstance(data, dict) or set(data) != {_WRAPPER_KEY} or not isinstance(data[_WRAPPER_KEY], dict):
        raise SidecarError(f'sidecar must be an object with only a "{_WRAPPER_KEY}" object')

    try:
        return Sidecar.model_validate(data[_WRAPPER_KEY])
    except ValidationError as error:
        raise SidecarError(f"sidecar has invalid metadata: {error}") from error


def check(sidecar: Sidecar, source: SourceDefinition) -> None:
    """Check that a sidecar fits the source its document belongs to.

    Args:
        sidecar: The metadata to check.
        source: The source the document was read from.

    Raises:
        SidecarError: If the document type is not the source's, or a field is set
            that the source does not declare.
    """
    if sidecar.document_type != source.document_type:
        raise SidecarError(
            f"document_type is {sidecar.document_type.value!r}, but the source's is {source.document_type.value!r}"
        )

    set_keys = set(sidecar.model_dump(exclude_none=True))
    not_allowed = sorted(set_keys - set(source.metadata_keys))
    if not_allowed:
        raise SidecarError(f"the source does not declare these keys: {', '.join(not_allowed)}")
