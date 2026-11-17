"""The metadata sidecar written next to every document.

A sidecar is a small JSON file in Bedrock's format, stored beside its document:

    files/case-123.pdf
    files/case-123.pdf.metadata.json

    {"metadataAttributes": {"document_type": "business_case", "date": 20250101}}

The knowledge bases read it as it is (the values are stored for filtering and are not
embedded), and the graph's text stage reads it to add the same fields to the extracted
text. Both go through this module, so they cannot disagree about the format.

`Sidecar` holds the fields. `date` is a real date in Python and is written as a number
`YYYYMMDD`, because Bedrock has no date type and filters ranges on numbers. `parse_date`
turns a partial date into a full one. `check` compares a sidecar with the keys its source
declares in `dia.sources.definitions`.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    Field,
    StrictBool,
    StringConstraints,
    ValidationError,
    field_serializer,
    field_validator,
)

from dia.document_types import DocumentType
from dia.sources.models import SourceDefinition

SIDECAR_SUFFIX = ".metadata.json"
# Bedrock: a metadata file "must not exceed the limit of 10 KB". Taken as 10,000 bytes, the stricter reading.
MAX_SIDECAR_BYTES = 10_000
_WRAPPER_KEY = "metadataAttributes"
# The earliest date that still writes as an 8-digit YYYYMMDD number.
_EARLIEST_DATE = dt.date(1000, 1, 1)

_Text = Annotated[str, StringConstraints(strict=True, min_length=1)]
_PARTIAL_DATE = re.compile(r"(\d{4})(?:(-?)(\d{2})(?:\2(\d{2}))?)?")


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
        report_type: The kind of report. Only NAO reports use it.
        spend_id: The spend control case ID (GATS and SR bids).
        project_name: The project the document belongs to.
        date: The document's own date, from the year 1000 on. Written as a number `YYYYMMDD`. When
            only the year or the month is known, use `parse_date`: it fills in the first month and
            the first day.
        is_latest: Whether it is the newest DBR document for its department.
    """

    document_type: DocumentType
    department_name: _Text | None = None
    alb: _Text | None = None
    report_type: _Text | None = None
    spend_id: _Text | None = None
    project_name: _Text | None = None
    date: dt.date | None = Field(default=None, strict=True, ge=_EARLIEST_DATE)
    is_latest: StrictBool | None = None

    @field_validator("date", mode="before")
    @classmethod
    def _date_from_number(cls, value: Any) -> Any:
        """Read the `YYYYMMDD` number a sidecar file holds. Anything else is left to the date check."""
        if isinstance(value, bool) or not isinstance(value, int):
            return value
        text = str(value)
        if len(text) != 8:
            raise ValueError(f"{value} is not a YYYYMMDD date")
        try:
            return dt.date(int(text[:4]), int(text[4:6]), int(text[6:]))
        except ValueError as error:
            raise ValueError(f"{value} is not a real date") from error

    @field_serializer("date", when_used="json")
    def _date_as_number(self, value: dt.date | None) -> int | None:
        """Write the date as the number `YYYYMMDD`."""
        return None if value is None else value.year * 10000 + value.month * 100 + value.day


def parse_date(text: str) -> dt.date:
    """Turn a date with only some parts into a full date, using the first of what is missing.

    Args:
        text: `YYYY`, `YYYYMM` or `YYYYMMDD`, or `YYYY-MM` or `YYYY-MM-DD`. The parts are
            either all joined with `-` or none are.

    Returns:
        The date. `2025` gives 1 January 2025, `2026-06` gives 1 June 2026.

    Raises:
        SidecarError: If the text is not in one of those forms, or is not a real date.
    """
    match = _PARTIAL_DATE.fullmatch(text.strip())
    if match is None:
        raise SidecarError(f"{text!r} is not a date like 2025, 202606 or 20260901")
    year, _separator, month, day = match.groups()
    parts = [int(part) if part else 1 for part in (year, month, day)]
    try:
        return dt.date(*parts)
    except ValueError as error:
        raise SidecarError(f"{text!r} is not a real date") from error


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
    if is_sidecar_key(document_key):
        raise SidecarError(f"{document_key!r} is already a sidecar key")
    return f"{document_key}{SIDECAR_SUFFIX}"


def is_sidecar_key(key: str) -> bool:
    """Whether an S3 key is a sidecar file, not a document.

    Args:
        key: Any key under a source's prefix.

    Returns:
        True if the key ends with `.metadata.json`.
    """
    return key.endswith(SIDECAR_SUFFIX)


def to_json(sidecar: Sidecar) -> str:
    """Write a sidecar in Bedrock's format, leaving out the fields that are not set.

    Args:
        sidecar: The metadata to write.

    Returns:
        The JSON text for the sidecar file.

    Raises:
        SidecarError: If the text is longer than `MAX_SIDECAR_BYTES`, Bedrock's limit for a
            metadata file.
    """
    attributes = sidecar.model_dump(mode="json", exclude_none=True)
    text = json.dumps({_WRAPPER_KEY: attributes}, indent=2)
    size = len(text.encode("utf-8"))
    if size > MAX_SIDECAR_BYTES:
        raise SidecarError(f"sidecar is {size} bytes, over the {MAX_SIDECAR_BYTES} byte limit for a metadata file")
    return text


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
