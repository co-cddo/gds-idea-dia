"""Resolves department names to filenames and SpendID prefixes.

Two metadata sources feed into department resolution:

- Historic metadata: a CSV mapping individual filenames directly to a
  department (and/or an Arm's Length Body). Used for older documents
  that predate SpendID-based naming.
- GATS metadata: the latest spend-controls export, mapping each SpendID
  to the department that submitted it. Documents are named with the
  SpendID as a prefix (e.g. "CS-100_report.pdf").

Department name matching here is exact-string — callers are responsible
for passing already-canonical department names (e.g. after applying any
raw-name normalisation/mapping upstream).
"""

from dia.filters.department import DepartmentFilter

_HISTORIC_DEPARTMENT_FIELD = "department"
_HISTORIC_ALB_FIELD = "alb"
_HISTORIC_FILENAME_FIELD = "filenames"

_GATS_SUBMITTER_FIELD = "CO_OrganisationSubmitter"
_GATS_SPEND_ID_FIELD = "CO_SpendID"


def resolve_department_filter(
    departments: list[str],
    historic_records: list[dict] | None = None,
    gats_records: list[dict] | None = None,
) -> DepartmentFilter:
    """Build a DepartmentFilter matching the given department names.

    Args:
        departments: Department names to match (e.g. ["Home Office"]).
            Matched exactly against both the historic 'department'/'alb'
            fields and the GATS submitter field.
        historic_records: Rows from the historic metadata CSV, each with
            'department', 'alb', and 'filenames' fields.
        gats_records: Rows from the latest GATS export, each with
            'CO_OrganisationSubmitter' and 'CO_SpendID' fields.

    Returns:
        A DepartmentFilter matching documents belonging to the given departments.
    """
    clean_departments = {d.strip() for d in departments if d and d.strip()}

    filenames = _resolve_historic_filenames(historic_records or [], clean_departments)
    prefixes = _resolve_gats_prefixes(gats_records or [], clean_departments)

    return DepartmentFilter(filenames=filenames, spend_id_prefixes=prefixes)


def _resolve_historic_filenames(records: list[dict], departments: set[str]) -> set[str]:
    """Find filenames belonging to the target departments in historic metadata."""
    if not departments:
        return set()

    filenames: set[str] = set()
    for row in records:
        department = str(row.get(_HISTORIC_DEPARTMENT_FIELD, "")).strip()
        alb = str(row.get(_HISTORIC_ALB_FIELD, "")).strip()

        if department in departments or alb in departments:
            filename = row.get(_HISTORIC_FILENAME_FIELD)
            if filename and str(filename).strip():
                filenames.add(str(filename).strip())

    return filenames


def _resolve_gats_prefixes(records: list[dict], departments: set[str]) -> set[str]:
    """Find SpendID prefixes belonging to the target departments in GATS metadata."""
    if not departments:
        return set()

    prefixes: set[str] = set()
    for row in records:
        submitter = str(row.get(_GATS_SUBMITTER_FIELD, "")).strip()

        if submitter in departments:
            spend_id = row.get(_GATS_SPEND_ID_FIELD)
            if spend_id and str(spend_id).strip():
                prefixes.add(str(spend_id).strip())

    return prefixes
