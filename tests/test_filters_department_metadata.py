"""Tests for dia.filters.department_metadata — resolving departments to filters."""

from dia.filters.department_metadata import resolve_department_filter

# ---------------------------------------------------------------------------
# Historic metadata resolution (exact filenames)
# ---------------------------------------------------------------------------


def test_resolves_filenames_by_department():
    historic = [
        {"department": "Home Office", "alb": "", "filenames": "report_a.pdf"},
        {"department": "HMRC", "alb": "", "filenames": "report_b.pdf"},
    ]

    filter_ = resolve_department_filter(["Home Office"], historic_records=historic)

    assert filter_.filenames == {"report_a.pdf"}


def test_resolves_filenames_by_alb():
    historic = [
        {"department": "", "alb": "Companies House", "filenames": "report_a.pdf"},
        {"department": "HMRC", "alb": "", "filenames": "report_b.pdf"},
    ]

    filter_ = resolve_department_filter(["Companies House"], historic_records=historic)

    assert filter_.filenames == {"report_a.pdf"}


def test_multiple_departments_combine_filenames():
    historic = [
        {"department": "Home Office", "alb": "", "filenames": "a.pdf"},
        {"department": "HMRC", "alb": "", "filenames": "b.pdf"},
        {"department": "DWP", "alb": "", "filenames": "c.pdf"},
    ]

    filter_ = resolve_department_filter(["Home Office", "HMRC"], historic_records=historic)

    assert filter_.filenames == {"a.pdf", "b.pdf"}


def test_missing_filename_field_skipped():
    historic = [
        {"department": "Home Office", "alb": "", "filenames": ""},
        {"department": "Home Office", "alb": "", "filenames": "b.pdf"},
    ]

    filter_ = resolve_department_filter(["Home Office"], historic_records=historic)

    assert filter_.filenames == {"b.pdf"}


def test_no_historic_records_gives_empty_filenames():
    filter_ = resolve_department_filter(["Home Office"], historic_records=[])

    assert filter_.filenames == set()


def test_none_historic_records_gives_empty_filenames():
    filter_ = resolve_department_filter(["Home Office"], historic_records=None)

    assert filter_.filenames == set()


# ---------------------------------------------------------------------------
# GATS metadata resolution (SpendID prefixes)
# ---------------------------------------------------------------------------


def test_resolves_spend_id_prefixes_by_submitter():
    gats = [
        {"CO_OrganisationSubmitter": "Home Office", "CO_SpendID": "CS-100"},
        {"CO_OrganisationSubmitter": "HMRC", "CO_SpendID": "CS-200"},
    ]

    filter_ = resolve_department_filter(["Home Office"], gats_records=gats)

    assert filter_.spend_id_prefixes == {"CS-100"}


def test_multiple_departments_combine_spend_ids():
    gats = [
        {"CO_OrganisationSubmitter": "Home Office", "CO_SpendID": "CS-100"},
        {"CO_OrganisationSubmitter": "HMRC", "CO_SpendID": "CS-200"},
        {"CO_OrganisationSubmitter": "DWP", "CO_SpendID": "CS-300"},
    ]

    filter_ = resolve_department_filter(["Home Office", "HMRC"], gats_records=gats)

    assert filter_.spend_id_prefixes == {"CS-100", "CS-200"}


def test_missing_spend_id_field_skipped():
    gats = [
        {"CO_OrganisationSubmitter": "Home Office", "CO_SpendID": ""},
        {"CO_OrganisationSubmitter": "Home Office", "CO_SpendID": "CS-100"},
    ]

    filter_ = resolve_department_filter(["Home Office"], gats_records=gats)

    assert filter_.spend_id_prefixes == {"CS-100"}


def test_no_gats_records_gives_empty_prefixes():
    filter_ = resolve_department_filter(["Home Office"], gats_records=[])

    assert filter_.spend_id_prefixes == set()


# ---------------------------------------------------------------------------
# Combined resolution
# ---------------------------------------------------------------------------


def test_combines_historic_and_gats_sources():
    historic = [{"department": "Home Office", "alb": "", "filenames": "legacy.pdf"}]
    gats = [{"CO_OrganisationSubmitter": "Home Office", "CO_SpendID": "CS-100"}]

    filter_ = resolve_department_filter(["Home Office"], historic_records=historic, gats_records=gats)

    assert filter_.filenames == {"legacy.pdf"}
    assert filter_.spend_id_prefixes == {"CS-100"}


def test_resulting_filter_matches_documents():
    """End-to-end: resolve then filter a document list."""
    from dia.types import DocumentReference

    historic = [{"department": "Home Office", "alb": "", "filenames": "legacy.pdf"}]
    gats = [{"CO_OrganisationSubmitter": "Home Office", "CO_SpendID": "CS-100"}]

    filter_ = resolve_department_filter(["Home Office"], historic_records=historic, gats_records=gats)

    refs = [
        DocumentReference(key="docs/legacy.pdf", content_type="application/pdf", version="v1"),
        DocumentReference(key="docs/CS-100_report.pdf", content_type="application/pdf", version="v1"),
        DocumentReference(key="docs/unrelated.pdf", content_type="application/pdf", version="v1"),
    ]

    result = filter_.filter(refs)

    keys = {r.key for r in result}
    assert keys == {"docs/legacy.pdf", "docs/CS-100_report.pdf"}


# ---------------------------------------------------------------------------
# Department name handling
# ---------------------------------------------------------------------------


def test_department_names_are_stripped():
    historic = [{"department": "Home Office", "alb": "", "filenames": "a.pdf"}]

    filter_ = resolve_department_filter(["  Home Office  "], historic_records=historic)

    assert filter_.filenames == {"a.pdf"}


def test_empty_department_list_matches_nothing():
    historic = [{"department": "Home Office", "alb": "", "filenames": "a.pdf"}]
    gats = [{"CO_OrganisationSubmitter": "Home Office", "CO_SpendID": "CS-100"}]

    filter_ = resolve_department_filter([], historic_records=historic, gats_records=gats)

    assert filter_.filenames == set()
    assert filter_.spend_id_prefixes == set()


def test_blank_department_names_filtered_out():
    historic = [{"department": "Home Office", "alb": "", "filenames": "a.pdf"}]

    filter_ = resolve_department_filter(["", "  ", "Home Office"], historic_records=historic)

    assert filter_.filenames == {"a.pdf"}
