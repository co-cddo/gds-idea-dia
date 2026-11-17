"""Turn rows of the GATS business case export into metadata sidecars.

The export has one row per case, and a case can list several documents. This module turns
a row into one `DocumentSidecar` per listed document, and picks which documents to label
when only some are wanted. It reads no bucket and writes nothing: the command that uses it
reads the export, and writes each sidecar next to its document.

Two layouts of the export exist, and they name some columns differently:

    older export (`spend-controls-raw-data/`):  CO_CS_Files, CO_CS_CaseName
    newer export (`spend-controls-raw-data/gas/`):  CO_I_Documents, CO_I_Name

Both layouts share `CO_SpendID`, `CO_OrganisationSubmitter` and `CO_CaseSubmitDate`.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from dia.department_mapping import PARENT_MAP
from dia.sources.definitions import SOURCES
from dia.sources.sidecar import Sidecar, SidecarError, check, parse_date

SOURCE_NAME = "gats_business_cases"

# The column that lists a case's files, by export layout. The first one with a value is used.
FILE_LIST_COLUMNS: tuple[str, ...] = ("CO_CS_Files", "CO_I_Documents")
# The column that holds the case's name, by export layout. The first one with a value is used.
NAME_COLUMNS: tuple[str, ...] = ("CO_CS_CaseName", "CO_I_Name")
SPEND_ID_COLUMN = "CO_SpendID"
SUBMITTER_COLUMN = "CO_OrganisationSubmitter"
SUBMIT_DATE_COLUMN = "CO_CaseSubmitDate"

Row = Mapping[str, Any]


def _clean(value: object) -> str | None:
    """A cell's text with the whitespace trimmed, or `None` if it is empty or `nan`."""
    if value is None:
        return None
    text = str(value).strip()
    return text if text and text.lower() != "nan" else None


def _first_value(row: Row, columns: tuple[str, ...]) -> str | None:
    """The first non-empty cell among `columns`, which are alternatives for one thing."""
    for column in columns:
        value = _clean(row.get(column))
        if value is not None:
            return value
    return None


def _file_names(row: Row) -> list[str]:
    """The file names a case lists, in order, without blanks or repeats.

    The cell is split on commas, so a file name that contains a comma is split in two.
    """
    cell = _first_value(row, FILE_LIST_COLUMNS)
    if cell is None:
        return []
    names = (name.strip() for name in cell.split(","))
    return list(dict.fromkeys(name for name in names if name))


def _submit_date(row: Row) -> dt.date | None:
    """The case's submit date.

    A time after the date (`2025-03-01T10:15:00` or `2025-03-01 10:15`) is ignored.

    Raises:
        SidecarError: If the cell has a value that is not a date.
    """
    text = _clean(row.get(SUBMIT_DATE_COLUMN))
    if text is None:
        return None
    return parse_date(text.replace("T", " ").split(" ")[0])


@dataclass(frozen=True)
class DocumentSidecar:
    """The metadata for one document, and the document it is for.

    The sidecar does not hold the file name: the label's content is the same for every
    document of a case, and the file is told apart by where the label is written.

    Attributes:
        file_name: The document's name as the export lists it, without a folder.
        sidecar: Its metadata.
    """

    file_name: str
    sidecar: Sidecar


def documents_for_row(row: Row) -> list[DocumentSidecar]:
    """Make a `DocumentSidecar` for each document one export row lists.

    Every document of the row gets the same metadata. The department is the submitter's
    parent department when the submitter is a known arm's-length body (and the submitter
    is then the ALB). Any other submitter is taken to be a department, and the ALB is left
    empty. A submit date that is empty or cannot be read leaves `date` out, and the
    documents are still returned.

    Args:
        row: One row of either export layout, by column name.

    Returns:
        One entry per listed document, in the order the export lists them. Empty if the row
        lists none.
    """
    source = SOURCES[SOURCE_NAME]

    try:
        submitted = _submit_date(row)
    except SidecarError:
        submitted = None

    submitter = _clean(row.get(SUBMITTER_COLUMN))
    sidecar = Sidecar(
        document_type=source.document_type,
        department_name=PARENT_MAP.get(submitter, submitter) if submitter else None,
        alb=submitter if submitter in PARENT_MAP else None,
        spend_id=_clean(row.get(SPEND_ID_COLUMN)),
        project_name=_first_value(row, NAME_COLUMNS),
        date=submitted,
    )
    check(sidecar, source)

    return [DocumentSidecar(name, sidecar) for name in _file_names(row)]


def choose_documents(
    documents: Iterable[DocumentSidecar],
    limit: int | None = None,
    departments: Iterable[str] | None = None,
) -> list[DocumentSidecar]:
    """Choose which documents to label: the newest ones, optionally for some departments.

    The departments are applied first and the limit last, so "10 documents for the Home
    Office" gives ten Home Office documents. A department matches on the sidecar's
    `department_name`, ignoring case and extra spaces, so a department includes its
    arm's-length bodies. Documents are ordered newest first by their sidecar's date, those
    with no date last. Documents with the same date keep the order they were given in
    (and cases with the same date are ordered by spend ID), so a repeat run chooses the
    same documents.

    Args:
        documents: Documents from `documents_for_row`, for any number of rows.
        limit: The most documents to choose, or `None` for all of them.
        departments: Department names to keep, or `None` for every department.

    Returns:
        The chosen documents, newest first.

    Raises:
        ValueError: If `limit` is below 1.
    """
    if limit is not None and limit < 1:
        raise ValueError("limit must be at least 1")

    chosen = list(documents)
    if departments is not None:
        wanted = {_normalise(name) for name in departments}
        chosen = [d for d in chosen if d.sidecar.department_name and _normalise(d.sidecar.department_name) in wanted]

    def newest_first(document: DocumentSidecar) -> tuple[bool, int, str]:
        date = document.sidecar.date
        return (date is None, -date.toordinal() if date else 0, document.sidecar.spend_id or "")

    chosen.sort(key=newest_first)
    return chosen if limit is None else chosen[:limit]


def _normalise(name: str) -> str:
    """A department name in a form to compare: lower case, with spaces collapsed."""
    return " ".join(name.split()).casefold()
