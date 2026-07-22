"""Filters documents by department using filename and SpendID matching.

Matches documents in two ways, mirroring how department metadata is
structured across historic and GATS-era document naming:

1. Exact filename match — for historic documents where a metadata CSV
   maps individual filenames directly to a department.
2. SpendID prefix match — for GATS-era documents named with a SpendID
   prefix (e.g. "CS-100_business_case.pdf" belongs to SpendID "CS-100").

Department name resolution (turning "Home Office" into a set of filenames
and SpendID prefixes) is a separate concern — see department_metadata.py.
This class only does the matching once those sets are known.
"""

from dia.types import DocumentReference

_PREFIX_SEPARATORS = ("_", " ", ".")


class DepartmentFilter:
    """Filters document references belonging to specific departments.

    Args:
        filenames: Exact filenames to match (from historic metadata).
        spend_id_prefixes: SpendID prefixes to match against filenames
            (from GATS metadata). A filename matches if it starts with
            one of these prefixes followed by a separator.
    """

    def __init__(self, filenames: set[str], spend_id_prefixes: set[str]) -> None:
        self._filenames = filenames
        self._prefixes = spend_id_prefixes

    @property
    def filenames(self) -> set[str]:
        """Exact filenames this filter matches (useful for tests/inspection)."""
        return self._filenames

    @property
    def spend_id_prefixes(self) -> set[str]:
        """SpendID prefixes this filter matches (useful for tests/inspection)."""
        return self._prefixes

    def filter(self, refs: list[DocumentReference]) -> list[DocumentReference]:
        """Return only the refs matching the configured departments."""
        return [ref for ref in refs if self._matches(ref.key)]

    def _matches(self, key: str) -> bool:
        """Check whether a document key belongs to the target departments."""
        filename = key.rsplit("/", 1)[-1]

        if filename in self._filenames:
            return True

        return self._matches_spend_id_prefix(filename)

    def _matches_spend_id_prefix(self, filename: str) -> bool:
        """Check whether the filename starts with a known SpendID prefix.

        Tries standard separators first (e.g. "CS-100_report.pdf" ->
        "CS-100"), then falls back to hyphen-based extraction for
        filenames like "CS-100-v2.pdf" where the SpendID itself contains
        a hyphen followed by digits.
        """
        if not self._prefixes:
            return False

        for sep in _PREFIX_SEPARATORS:
            if sep in filename:
                candidate = filename.split(sep, 1)[0].strip()
                if candidate in self._prefixes:
                    return True

        return self._matches_hyphenated_spend_id(filename)

    def _matches_hyphenated_spend_id(self, filename: str) -> bool:
        """Extract a "prefix-digits" candidate from a hyphenated filename.

        Handles SpendIDs like "CS-100" where the filename has no other
        separator, e.g. "CS-100-final-version.pdf" -> candidate "CS-100".
        """
        if filename.count("-") < 1:
            return False

        parts = filename.split("-")
        if len(parts) < 2:
            return False

        prefix = parts[0].strip()
        digits = ""
        for char in parts[1].strip():
            if char.isdigit():
                digits += char
            else:
                break

        if not digits:
            return False

        candidate = f"{prefix}-{digits}"
        return candidate in self._prefixes
