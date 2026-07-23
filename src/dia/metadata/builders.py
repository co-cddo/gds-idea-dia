"""Pure functions that build a metadata lookup from raw records.

Each builder corresponds to a metadata strategy used by one or more
sources. All builders take plain `list[dict]` records (no pandas, no S3)
and return a lookup keyed by full document key (source prefix + filename),
so they're trivially testable with fixture data.
"""

from dia.department_mapping import PARENT_MAP
from dia.metadata.models import DocumentMetadata


def build_historic_csv_lookup(records: list[dict], prefix: str) -> dict[str, DocumentMetadata]:
    """Build a lookup from a historic metadata CSV.

    Expects rows with a filename field (tries 'filenames', 'filename',
    'file_name', 'file' in that order — different CSVs use different
    names for this) plus optional 'department', 'alb', 'spend_id',
    'project_name' fields.

    Args:
        records: Rows from the historic metadata CSV.
        prefix: The source's key prefix, prepended to each filename to
            build the full document key.

    Returns:
        Lookup keyed by full document key (prefix + filename).
    """
    lookup: dict[str, DocumentMetadata] = {}

    for row in records:
        filename = _clean(row.get("filenames") or row.get("filename") or row.get("file_name") or row.get("file"))
        if not filename:
            continue

        key = f"{prefix}{filename}"
        lookup[key] = DocumentMetadata(
            department=_clean(row.get("department")),
            alb=_clean(row.get("alb")),
            spend_id=_clean(row.get("spend_id")),
            project_name=_clean(row.get("project_name")),
        )

    return lookup


def build_gats_lookup(
    historic_records: list[dict],
    gats_records: list[dict],
    prefix: str,
) -> dict[str, DocumentMetadata]:
    """Build a lookup combining historic metadata with the latest GATS export.

    GATS records take priority over historic records for the same filename
    (GATS is the more current, structured source). GATS rows may reference
    multiple filenames via a comma-separated 'CO_CS_Files' field — each one
    gets its own lookup entry with the same metadata.

    ALB names (CO_OrganisationSubmitter) are mapped to their parent
    department via PARENT_MAP where a mapping exists; otherwise the raw
    submitter name is used as the department.

    Args:
        historic_records: Rows from the historic metadata CSV.
        gats_records: Rows from the latest GATS spend-controls export.
        prefix: The source's key prefix, prepended to each filename.

    Returns:
        Lookup keyed by full document key (prefix + filename).
    """
    lookup = build_historic_csv_lookup(historic_records, prefix)

    for row in gats_records:
        files_field = row.get("CO_CS_Files", "")
        if not files_field:
            continue

        filenames = [f.strip() for f in str(files_field).split(",") if f.strip()]
        if not filenames:
            continue

        submitter = _clean(row.get("CO_OrganisationSubmitter"))
        department = PARENT_MAP.get(submitter, submitter) if submitter else None

        metadata = DocumentMetadata(
            department=department,
            alb=submitter,
            spend_id=_clean(row.get("CO_SpendID")),
            project_name=_clean(row.get("CO_CS_CaseName")),
            assurance_date=_clean(row.get("CO_AssuranceRatingRequestedDate")),
        )

        for filename in filenames:
            key = f"{prefix}{filename}"
            lookup[key] = metadata

    return lookup


def build_folder_name_lookup(keys: list[str], prefix: str) -> dict[str, DocumentMetadata]:
    """Derive metadata from folder structure: prefix/Department Name/filename.ext.

    Used for sources with no metadata CSV, where department is encoded
    directly in the S3 key structure (e.g. "sr21-bids/Home Office/Project Alpha.docx").
    The folder name is mapped through PARENT_MAP in case it's an ALB or
    abbreviation rather than a canonical department name.

    Args:
        keys: Full document keys (as returned by source.list_documents()).
        prefix: The source's key prefix, stripped before parsing folder structure.

    Returns:
        Lookup keyed by the original full document key.
    """
    lookup: dict[str, DocumentMetadata] = {}

    for key in keys:
        relative = key[len(prefix) :] if key.startswith(prefix) else key
        parts = relative.split("/")

        if len(parts) < 2:
            continue

        folder_name = parts[0].strip()
        if not folder_name:
            continue

        department = PARENT_MAP.get(folder_name, folder_name)
        alb = folder_name if department != folder_name else None

        filename = parts[-1].strip()
        project_name = filename.rsplit(".", 1)[0].strip() if "." in filename else filename

        lookup[key] = DocumentMetadata(department=department, alb=alb, project_name=project_name or None)

    return lookup


def _clean(value: object) -> str | None:
    """Clean a CSV field value — strip whitespace, treat empty/NaN as None."""
    if value is None:
        return None
    text = str(value).strip()
    return text if text and text.lower() != "nan" else None
