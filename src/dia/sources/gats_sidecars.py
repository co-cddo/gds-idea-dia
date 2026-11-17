"""Turn rows of the GATS business case export into metadata sidecars.

A row is one case, and lists the documents it covers. This module gives each listed
document a `DocumentSidecar`, and picks which documents to label. It does no S3 work.

The export has two layouts, with different names for the file list and the case name:
older (`CO_CS_Files`, `CO_CS_CaseName`) and newer (`CO_I_Documents`, `CO_I_Name`).
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

FILE_LIST_COLUMNS = ("CO_CS_Files", "CO_I_Documents")
NAME_COLUMNS = ("CO_CS_CaseName", "CO_I_Name")
SPEND_ID_COLUMN = "CO_SpendID"
SUBMITTER_COLUMN = "CO_OrganisationSubmitter"
SUBMIT_DATE_COLUMN = "CO_CaseSubmitDate"

Row = Mapping[str, Any]


def _normalise(name: str) -> str:
    return " ".join(name.split()).casefold()


_ALBS = {_normalise(alb): (alb, parent) for alb, parent in PARENT_MAP.items()}
_DEPARTMENTS = {_normalise(parent): parent for parent in PARENT_MAP.values()}


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text and text.lower() != "nan" else None


def _first_value(row: Row, columns: tuple[str, ...]) -> str | None:
    for column in columns:
        value = _clean(row.get(column))
        if value is not None:
            return value
    return None


def _file_names(row: Row) -> list[str]:
    cell = _first_value(row, FILE_LIST_COLUMNS)
    if cell is None:
        return []
    names = (name.strip() for name in cell.split(","))
    return list(dict.fromkeys(name for name in names if name))


def _submit_date(row: Row) -> dt.date | None:
    text = _clean(row.get(SUBMIT_DATE_COLUMN))
    if text is None:
        return None
    return parse_date(text.replace("T", " ").split(" ")[0])


def _department_and_alb(submitter: str | None) -> tuple[str | None, str | None]:
    if submitter is None:
        return None, None
    key = _normalise(submitter)
    if key in _ALBS:
        alb, parent = _ALBS[key]
        return parent, alb
    return _DEPARTMENTS.get(key, submitter), None


@dataclass(frozen=True)
class DocumentSidecar:
    """A document's name and its metadata. The name is not part of the metadata."""

    file_name: str
    sidecar: Sidecar


def documents_for_row(row: Row) -> list[DocumentSidecar]:
    """Give each document the row lists the same metadata.

    A known ALB gives its parent as the department. A known department is written in its
    canonical spelling. Any other submitter is kept as written, with no ALB. A date that is
    empty or unreadable is left out.
    """
    source = SOURCES[SOURCE_NAME]

    try:
        submitted = _submit_date(row)
    except SidecarError:
        submitted = None

    department, alb = _department_and_alb(_clean(row.get(SUBMITTER_COLUMN)))
    sidecar = Sidecar(
        document_type=source.document_type,
        department_name=department,
        alb=alb,
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
    """Pick the newest documents, optionally only for some departments.

    Departments are applied first, then the newest-first order, then the limit. Documents
    with no date come last. `limit` counts documents.
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
