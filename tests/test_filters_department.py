"""Tests for dia.filters.department — DepartmentFilter matching logic."""

from dia.filters.department import DepartmentFilter
from dia.types import DocumentReference


def _ref(key: str) -> DocumentReference:
    return DocumentReference(key=key, content_type="application/pdf", version="v1")


# ---------------------------------------------------------------------------
# Exact filename matching (historic documents)
# ---------------------------------------------------------------------------


def test_matches_exact_filename():
    filter_ = DepartmentFilter(filenames={"report.pdf"}, spend_id_prefixes=set())
    refs = [_ref("docs/report.pdf"), _ref("docs/other.pdf")]

    result = filter_.filter(refs)

    assert [r.key for r in result] == ["docs/report.pdf"]


def test_exact_match_ignores_path_prefix():
    filter_ = DepartmentFilter(filenames={"report.pdf"}, spend_id_prefixes=set())
    refs = [_ref("files/nested/deep/report.pdf")]

    result = filter_.filter(refs)

    assert len(result) == 1


def test_no_filenames_or_prefixes_matches_nothing():
    filter_ = DepartmentFilter(filenames=set(), spend_id_prefixes=set())
    refs = [_ref("docs/report.pdf"), _ref("docs/other.pdf")]

    result = filter_.filter(refs)

    assert result == []


# ---------------------------------------------------------------------------
# SpendID prefix matching (GATS-era documents) — separator strategies
# ---------------------------------------------------------------------------


def test_matches_spend_id_with_underscore_separator():
    filter_ = DepartmentFilter(filenames=set(), spend_id_prefixes={"CS-100"})
    refs = [_ref("files/CS-100_business_case.pdf")]

    result = filter_.filter(refs)

    assert len(result) == 1


def test_matches_spend_id_with_space_separator():
    filter_ = DepartmentFilter(filenames=set(), spend_id_prefixes={"CS-100"})
    refs = [_ref("files/CS-100 business case.pdf")]

    result = filter_.filter(refs)

    assert len(result) == 1


def test_matches_spend_id_with_dot_separator():
    filter_ = DepartmentFilter(filenames=set(), spend_id_prefixes={"CS-100"})
    refs = [_ref("files/CS-100.pdf")]

    result = filter_.filter(refs)

    assert len(result) == 1


def test_matches_spend_id_via_hyphen_fallback():
    """Filename with no other separator — extract prefix + leading digits after hyphen."""
    filter_ = DepartmentFilter(filenames=set(), spend_id_prefixes={"CS-100"})
    refs = [_ref("files/CS-100-final-version.pdf")]

    result = filter_.filter(refs)

    assert len(result) == 1


def test_non_matching_spend_id_prefix_excluded():
    filter_ = DepartmentFilter(filenames=set(), spend_id_prefixes={"CS-100"})
    refs = [_ref("files/CS-999_report.pdf")]

    result = filter_.filter(refs)

    assert result == []


def test_empty_prefixes_never_matches_via_prefix():
    filter_ = DepartmentFilter(filenames=set(), spend_id_prefixes=set())
    refs = [_ref("files/CS-100_report.pdf")]

    result = filter_.filter(refs)

    assert result == []


# ---------------------------------------------------------------------------
# Combined matching
# ---------------------------------------------------------------------------


def test_matches_via_either_filename_or_prefix():
    filter_ = DepartmentFilter(filenames={"legacy.pdf"}, spend_id_prefixes={"CS-100"})
    refs = [
        _ref("docs/legacy.pdf"),
        _ref("docs/CS-100_report.pdf"),
        _ref("docs/unrelated.pdf"),
    ]

    result = filter_.filter(refs)

    keys = {r.key for r in result}
    assert keys == {"docs/legacy.pdf", "docs/CS-100_report.pdf"}


def test_empty_refs_returns_empty():
    filter_ = DepartmentFilter(filenames={"a.pdf"}, spend_id_prefixes={"CS-100"})

    result = filter_.filter([])

    assert result == []


def test_preserves_ref_order():
    filter_ = DepartmentFilter(filenames={"a.pdf", "b.pdf", "c.pdf"}, spend_id_prefixes=set())
    refs = [_ref("c.pdf"), _ref("a.pdf"), _ref("b.pdf")]

    result = filter_.filter(refs)

    assert [r.key for r in result] == ["c.pdf", "a.pdf", "b.pdf"]


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


def test_filenames_property_exposes_configured_set():
    filter_ = DepartmentFilter(filenames={"a.pdf", "b.pdf"}, spend_id_prefixes=set())

    assert filter_.filenames == {"a.pdf", "b.pdf"}


def test_spend_id_prefixes_property_exposes_configured_set():
    filter_ = DepartmentFilter(filenames=set(), spend_id_prefixes={"CS-100", "CS-200"})

    assert filter_.spend_id_prefixes == {"CS-100", "CS-200"}


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_filename_with_no_separator_and_no_hyphen_does_not_match_prefix():
    filter_ = DepartmentFilter(filenames=set(), spend_id_prefixes={"CS-100"})
    refs = [_ref("files/report.pdf")]

    result = filter_.filter(refs)

    assert result == []


def test_single_part_after_hyphen_split_does_not_crash():
    """A filename like 'report-.pdf' splits to ['report', '.pdf'] — no digits after hyphen."""
    filter_ = DepartmentFilter(filenames=set(), spend_id_prefixes={"CS-100"})
    refs = [_ref("report-.pdf")]

    result = filter_.filter(refs)

    assert result == []


def test_hyphen_with_no_digits_does_not_match():
    filter_ = DepartmentFilter(filenames=set(), spend_id_prefixes={"CS-abc"})
    refs = [_ref("CS-abc-final.pdf")]

    # No digits immediately after the hyphen in "abc-final" -> candidate is "CS-" (no digits)
    result = filter_.filter(refs)

    assert result == []
