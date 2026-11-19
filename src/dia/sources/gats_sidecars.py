"""Turn rows of the GATS business case export into metadata sidecars.

A row is one case, and lists the documents it covers. This module gives each listed
document a `Sidecar`, as a dict of file name to sidecar, and picks which documents to
label. A file listed by two rows keeps the sidecar of the row merged in last. It reads the
export from S3 and writes nothing.

The export has two layouts, with different names for the file list and the case name:
older (`CO_CS_Files`, `CO_CS_CaseName`) and newer (`CO_I_Documents`, `CO_I_Name`).
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import sys
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
DATE_COLUMNS = ("CO_SpendStartDate", "CO_DT_SpendStartDate", "CO_CaseSubmitDate")
DATE_FORMATS = ("%d %B %Y", "%d-%b-%y")
EARLIEST_DATE = dt.date(1990, 1, 1)

OLD_EXPORT_PREFIX = "spend-controls-raw-data/"
NEW_EXPORT_PREFIX = "spend-controls-raw-data/gas/"
LATEST = "latest"


class ExportError(Exception):
    """The export could not be found or read."""


def latest_export_key(s3_client: Any, bucket: str) -> str:
    """Return the key of the newest CSV under `NEW_EXPORT_PREFIX`.

    Newest means most recently modified. Files modified at the same moment are ordered by
    key, so the choice is repeatable. The dates in the keys are day-month-year, so this
    order is not chronological.

    Raises:
        ExportError: If there is no CSV there.
    """
    csvs: list[tuple[dt.datetime, str]] = []
    for page in s3_client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=NEW_EXPORT_PREFIX):
        csvs += [
            (item["LastModified"], item["Key"])
            for item in page.get("Contents", [])
            if item["Key"].lower().endswith(".csv")
        ]
    if not csvs:
        raise ExportError(f"no CSV export under s3://{bucket}/{NEW_EXPORT_PREFIX}")
    return max(csvs)[1]


def export_key(s3_client: Any, bucket: str, export: str) -> str:
    """Return the full key of the export the user asked for.

    `latest` gives the newest CSV under `NEW_EXPORT_PREFIX`. A bare file name (no `/`) is
    looked for under `OLD_EXPORT_PREFIX`. Any other value is already a key.

    Raises:
        ExportError: If `latest` finds no CSV.
    """
    if export == LATEST:
        return latest_export_key(s3_client, bucket)
    return export if "/" in export else OLD_EXPORT_PREFIX + export


def read_export(s3_client: Any, bucket: str, key: str) -> list[dict[str, str]]:
    """Return the rows of an export CSV, one dict per case, keyed by column name.

    Raises:
        ExportError: If the file does not exist.
    """
    try:
        body = s3_client.get_object(Bucket=bucket, Key=key)["Body"].read()
    except s3_client.exceptions.NoSuchKey:
        raise ExportError(f"s3://{bucket}/{key} does not exist") from None

    csv.field_size_limit(sys.maxsize)
    return list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"))))


def _name_key(name: str) -> str:
    """Return `name` in a form for comparing names: no extra spaces, ignoring case, `&` as `and`."""
    return " ".join(name.replace("&", " and ").split()).casefold()


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


def _read_date(text: str) -> dt.date:
    """Read a date in one of the forms the exports use, ignoring any time.

    Raises:
        SidecarError: If it is in none of those forms, or is before `EARLIEST_DATE`.
    """
    try:
        date = parse_date(text.replace("T", " ").split(" ")[0])
    except SidecarError:
        date = None
        for date_format in DATE_FORMATS:
            try:
                date = dt.datetime.strptime(text, date_format).date()
                break
            except ValueError:
                continue
        if date is None:
            raise SidecarError(f"{text!r} is not a date in a form the export uses") from None
    if date < EARLIEST_DATE:
        raise SidecarError(f"{text!r} is before {EARLIEST_DATE.year}")
    return date


def _case_date(row: Mapping[str, Any]) -> dt.date | None:
    """Return the row's date from the first of `DATE_COLUMNS` that has text, or `None` if none do.

    Raises:
        SidecarError: If that text is not a readable date.
    """
    text = _first_text(row, DATE_COLUMNS)
    return None if text is None else _read_date(text)


def unreadable_date(row: Mapping[str, Any]) -> str | None:
    """Return the row's date text as written if it has some that cannot be read, otherwise `None`.

    An empty date is not unreadable.
    """
    try:
        _case_date(row)
    except SidecarError:
        return _first_text(row, DATE_COLUMNS)
    return None


def _department_and_alb(submitter: str | None) -> tuple[str | None, str | None]:
    """Return `(department, alb)` for a submitter, in the spelling of `PARENT_MAP`."""
    if submitter is None:
        return None, None
    key = _name_key(submitter)
    if key in _ALBS:
        alb, parent = _ALBS[key]
        return parent, alb
    return _DEPARTMENTS.get(key, submitter), None


def unrecognised_submitter(row: Mapping[str, Any]) -> str | None:
    """Return the row's submitter as written if it is in neither the department nor the ALB list.

    Returns `None` if the submitter is known, or if the row has none.
    """
    submitter = _text_or_none(row.get(SUBMITTER_COLUMN))
    if submitter is None or _name_key(submitter) in _ALBS or _name_key(submitter) in _DEPARTMENTS:
        return None
    return submitter


def documents_for_row(row: Mapping[str, Any]) -> dict[str, Sidecar]:
    """Map each document the row lists, by file name, to the same metadata.

    A known ALB gives its parent as the department. A known department is written in its
    canonical spelling. Any other submitter is kept as written, with no ALB. The date is the
    first of `DATE_COLUMNS` that has text, and is left out if there is none or it is unreadable.
    """
    source = SOURCES[SOURCE_NAME]

    try:
        submitted = _case_date(row)
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


def unmatched_departments(documents: Mapping[str, Sidecar], departments: Iterable[str]) -> list[str]:
    """Return the requested departments that no document belongs to, as they were given.

    Matches the way `choose_documents` does: ignoring case and extra spaces.
    """
    present = {_name_key(sidecar.department_name) for sidecar in documents.values() if sidecar.department_name}
    return [name for name in departments if _name_key(name) not in present]
