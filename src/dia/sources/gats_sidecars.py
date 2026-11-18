"""Turn rows of the GATS business case export into metadata sidecars.

A row is one case, and lists the documents it covers. This module gives each listed
document a `Sidecar`, as a dict of file name to sidecar, and picks which documents to
label. A file listed by two rows keeps the sidecar of the row merged in last. It does no
S3 work.

The export has two layouts, with different names for the file list and the case name:
older (`CO_CS_Files`, `CO_CS_CaseName`) and newer (`CO_I_Documents`, `CO_I_Name`).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping
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


def _name_key(name: str) -> str:
    """Return `name` in a form for comparing names: no extra spaces, ignoring case."""
    return " ".join(name.split()).casefold()


_ALBS = {_name_key(alb): (alb, parent) for alb, parent in PARENT_MAP.items()}
_DEPARTMENTS = {_name_key(parent): parent for parent in PARENT_MAP.values()}


def _text_or_none(value: object) -> str | None:
    """Return the value as trimmed text, or `None` if it is missing, blank or `nan`."""
    if value is None:
        return None
    text = str(value).strip()
    return text if text and text.lower() != "nan" else None


def _first_text(row: Mapping[str, Any], columns: tuple[str, ...]) -> str | None:
    """Return the first of `columns` that has text in this row, or `None` if none do."""
    for column in columns:
        value = _text_or_none(row.get(column))
        if value is not None:
            return value
    return None


def _file_names(row: Mapping[str, Any]) -> list[str]:
    """Return the file names the row lists, in order, without blanks or repeats."""
    cell = _first_text(row, FILE_LIST_COLUMNS)
    if cell is None:
        return []
    names = (name.strip() for name in cell.split(","))
    return list(dict.fromkeys(name for name in names if name))


def _submit_date(row: Mapping[str, Any]) -> dt.date | None:
    """Return the date the case was submitted, ignoring any time. Raises `SidecarError` if unreadable."""
    text = _text_or_none(row.get(SUBMIT_DATE_COLUMN))
    if text is None:
        return None
    return parse_date(text.replace("T", " ").split(" ")[0])


def _department_and_alb(submitter: str | None) -> tuple[str | None, str | None]:
    """Return `(department, alb)` for a submitter, in the spelling of `PARENT_MAP`."""
    if submitter is None:
        return None, None
    key = _name_key(submitter)
    if key in _ALBS:
        alb, parent = _ALBS[key]
        return parent, alb
    return _DEPARTMENTS.get(key, submitter), None


def documents_for_row(row: Mapping[str, Any]) -> dict[str, Sidecar]:
    """Map each document the row lists, by file name, to the same metadata.

    A known ALB gives its parent as the department. A known department is written in its
    canonical spelling. Any other submitter is kept as written, with no ALB. A date that is
    empty or unreadable is left out.
    """
    source = SOURCES[SOURCE_NAME]

    try:
        submitted = _submit_date(row)
    except SidecarError:
        submitted = None

    department, alb = _department_and_alb(_text_or_none(row.get(SUBMITTER_COLUMN)))
    sidecar = Sidecar(
        document_type=source.document_type,
        department_name=department,
        alb=alb,
        spend_id=_text_or_none(row.get(SPEND_ID_COLUMN)),
        project_name=_first_text(row, NAME_COLUMNS),
        date=submitted,
    )
    check(sidecar, source)

    return dict.fromkeys(_file_names(row), sidecar)


def _newest_first(document: tuple[str, Sidecar]) -> tuple[bool, int, str]:
    """Sort key for a `(file name, sidecar)` pair: newest date first, no date last, then spend ID so runs repeat."""
    _, sidecar = document
    return (sidecar.date is None, -sidecar.date.toordinal() if sidecar.date else 0, sidecar.spend_id or "")


def choose_documents(
    documents: Mapping[str, Sidecar],
    limit: int | None = None,
    departments: Iterable[str] | None = None,
) -> dict[str, Sidecar]:
    """Pick the newest documents, optionally only for some departments.

    Departments are applied first, then the newest-first order, then the limit. Documents
    with no date come last. `limit` counts documents.
    """
    if limit is not None and limit < 1:
        raise ValueError("limit must be at least 1")

    chosen = list(documents.items())
    if departments is not None:
        wanted = {_name_key(name) for name in departments}
        chosen = [
            (name, sidecar)
            for name, sidecar in chosen
            if sidecar.department_name and _name_key(sidecar.department_name) in wanted
        ]

    chosen.sort(key=_newest_first)
    return dict(chosen if limit is None else chosen[:limit])
