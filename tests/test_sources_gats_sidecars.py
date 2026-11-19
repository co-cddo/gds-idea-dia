"""Tests for dia.sources.gats_sidecars: GATS export rows to document sidecars."""

import datetime as dt

import pytest

from dia.department_mapping import PARENT_MAP
from dia.document_types import DocumentType
from dia.sources.gats_sidecars import choose_documents, documents_for_row
from dia.sources.sidecar import Sidecar

OLD_ROW = {
    "CO_SpendID": "COSC-00001",
    "CO_OrganisationSubmitter": "Department for Education",
    "CO_CaseSubmitDate": "2025-03-01",
    "CO_CS_Files": "case.pdf, annex.docx",
    "CO_CS_CaseName": "School Data Platform",
}
GAS_ROW = {
    "CO_SpendID": "COSC-00002",
    "CO_OrganisationSubmitter": "Department for Education",
    "CO_CaseSubmitDate": "2026-02-10",
    "CO_I_Documents": "new.pdf",
    "CO_I_Name": "Pupil Records",
}
AN_ALB = next(iter(PARENT_MAP))


def _names(documents):
    return list(documents)


def _first_sidecar(documents):
    return next(iter(documents.values()))


def _documents(*documents):
    """Build the `{file name: sidecar}` dict from `_document(...)` pairs."""
    return dict(documents)


def _document(name, date=None, spend_id="X", department="Department for Education"):
    sidecar = Sidecar(
        document_type=DocumentType.BUSINESS_CASE,
        department_name=department,
        spend_id=spend_id,
        date=date,
    )
    return name, sidecar


# --- both export layouts ---


def test_older_layout_maps_every_field():
    documents = documents_for_row(OLD_ROW)
    assert _names(documents) == ["case.pdf", "annex.docx"]
    assert _first_sidecar(documents) == Sidecar(
        document_type=DocumentType.BUSINESS_CASE,
        department_name="Department for Education",
        spend_id="COSC-00001",
        project_name="School Data Platform",
        date=dt.date(2025, 3, 1),
    )


def test_newer_layout_takes_files_and_name_from_the_gas_columns():
    documents = documents_for_row(GAS_ROW)
    assert _names(documents) == ["new.pdf"]
    assert _first_sidecar(documents).project_name == "Pupil Records"
    assert _first_sidecar(documents).date == dt.date(2026, 2, 10)


def test_the_older_columns_win_when_a_row_has_both():
    documents = documents_for_row({**OLD_ROW, "CO_I_Documents": "other.pdf", "CO_I_Name": "Other"})
    assert _names(documents) == ["case.pdf", "annex.docx"]
    assert _first_sidecar(documents).project_name == "School Data Platform"


def test_every_document_of_a_row_gets_the_same_metadata():
    first, second = documents_for_row(OLD_ROW).values()
    assert first == second


def test_document_type_comes_from_the_source_declaration():
    assert _first_sidecar(documents_for_row(OLD_ROW)).document_type == DocumentType.BUSINESS_CASE


# --- file lists ---


def test_file_list_is_trimmed_and_drops_blanks_and_repeats():
    documents = documents_for_row({**OLD_ROW, "CO_CS_Files": " a.pdf ,, b.pdf , a.pdf,"})
    assert _names(documents) == ["a.pdf", "b.pdf"]


@pytest.mark.parametrize("cell", [None, "", "   ", "nan", "NaN"])
def test_a_row_with_no_files_gives_no_documents(cell):
    assert documents_for_row({**OLD_ROW, "CO_CS_Files": cell}) == {}


def test_an_empty_older_column_falls_back_to_the_gas_column():
    documents = documents_for_row({**GAS_ROW, "CO_CS_Files": "", "CO_CS_CaseName": "nan"})
    assert _names(documents) == ["new.pdf"]
    assert _first_sidecar(documents).project_name == "Pupil Records"


# --- department and ALB ---


def test_a_known_alb_gives_its_parent_department_and_is_the_alb():
    sidecar = _first_sidecar(documents_for_row({**OLD_ROW, "CO_OrganisationSubmitter": AN_ALB}))
    assert sidecar.department_name == PARENT_MAP[AN_ALB]
    assert sidecar.alb == AN_ALB


def test_any_other_submitter_is_the_department_and_there_is_no_alb():
    sidecar = _first_sidecar(documents_for_row(OLD_ROW))
    assert sidecar.department_name == "Department for Education"
    assert sidecar.alb is None


@pytest.mark.parametrize("submitter", [f"{AN_ALB} ", AN_ALB.upper(), AN_ALB.lower(), AN_ALB.replace(" ", "  ")])
def test_an_alb_is_found_ignoring_case_and_spaces_and_written_in_its_own_spelling(submitter):
    sidecar = _first_sidecar(documents_for_row({**OLD_ROW, "CO_OrganisationSubmitter": submitter}))
    assert sidecar.department_name == PARENT_MAP[AN_ALB]
    assert sidecar.alb == AN_ALB


@pytest.mark.parametrize("submitter", ["home office", "HOME  OFFICE ", "Home Office"])
def test_a_known_department_is_written_in_its_own_spelling(submitter):
    sidecar = _first_sidecar(documents_for_row({**OLD_ROW, "CO_OrganisationSubmitter": submitter}))
    assert sidecar.department_name == "Home Office"
    assert sidecar.alb is None


def test_an_unknown_submitter_is_kept_as_written_with_no_alb():
    sidecar = _first_sidecar(documents_for_row({**OLD_ROW, "CO_OrganisationSubmitter": "Some New Body"}))
    assert sidecar.department_name == "Some New Body"
    assert sidecar.alb is None


def test_a_missing_submitter_leaves_department_and_alb_out():
    sidecar = _first_sidecar(documents_for_row({**OLD_ROW, "CO_OrganisationSubmitter": ""}))
    assert sidecar.department_name is None
    assert sidecar.alb is None


# --- dates ---


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("2025-03-01", dt.date(2025, 3, 1)),
        ("20250301", dt.date(2025, 3, 1)),
        ("2025-03-01T10:15:00", dt.date(2025, 3, 1)),
        ("2025-03-01 10:15", dt.date(2025, 3, 1)),
        (" 2025-03-01 ", dt.date(2025, 3, 1)),
        ("2025-03", dt.date(2025, 3, 1)),
    ],
)
def test_submit_date_accepts_dates_with_or_without_a_time(cell, expected):
    documents = documents_for_row({**OLD_ROW, "CO_CaseSubmitDate": cell})
    assert _first_sidecar(documents).date == expected


@pytest.mark.parametrize("cell", ["", None, "nan", "01/03/2025", "March 2025", "2025-13-45", "soon"])
def test_a_date_that_is_empty_or_cannot_be_read_is_left_out_and_documents_are_kept(cell):
    documents = documents_for_row({**OLD_ROW, "CO_CaseSubmitDate": cell})
    assert _names(documents) == ["case.pdf", "annex.docx"]
    assert all(sidecar.date is None for sidecar in documents.values())


@pytest.mark.parametrize("cell", ["0001-01-01", "0999-12-31", "2026-0601", "202606-01"])
def test_placeholder_and_malformed_dates_do_not_crash_the_row(cell):
    documents = documents_for_row({**OLD_ROW, "CO_CaseSubmitDate": cell})
    assert _names(documents) == ["case.pdf", "annex.docx"]
    assert all(sidecar.date is None for sidecar in documents.values())


def test_the_earliest_accepted_date_is_the_year_1000():
    documents = documents_for_row({**OLD_ROW, "CO_CaseSubmitDate": "1000-01-01"})
    assert _first_sidecar(documents).date == dt.date(1000, 1, 1)


def test_a_row_with_no_spend_id_still_maps():
    documents = documents_for_row({**OLD_ROW, "CO_SpendID": None})
    assert _first_sidecar(documents).spend_id is None


# --- choose_documents: order and limit ---


def test_documents_come_newest_first():
    documents = _documents(
        _document("a", dt.date(2025, 1, 1)),
        _document("b", dt.date(2026, 1, 1)),
        _document("c", dt.date(2024, 1, 1)),
    )
    assert _names(choose_documents(documents)) == ["b", "a", "c"]


def test_limit_counts_documents_and_can_cut_a_case_part_way():
    newer = documents_for_row({**OLD_ROW, "CO_CaseSubmitDate": "2026-01-01", "CO_CS_Files": "n1,n2,n3"})
    older = documents_for_row({**OLD_ROW, "CO_CaseSubmitDate": "2025-01-01", "CO_CS_Files": "o1,o2,o3"})
    assert _names(choose_documents({**older, **newer}, limit=4)) == ["n1", "n2", "n3", "o1"]


def test_a_file_listed_by_two_rows_keeps_the_row_merged_last_and_uses_the_limit_once():
    older = documents_for_row({**OLD_ROW, "CO_CaseSubmitDate": "2025-01-01", "CO_CS_Files": "shared.pdf, o1"})
    newer = documents_for_row({**OLD_ROW, "CO_CaseSubmitDate": "2026-01-01", "CO_CS_Files": "shared.pdf, n1"})
    merged = {**older, **newer}
    assert merged["shared.pdf"].date == dt.date(2026, 1, 1)
    assert _names(choose_documents(merged, limit=3)) == ["shared.pdf", "n1", "o1"]


def test_limit_larger_than_the_data_returns_everything():
    documents = _documents(_document("a", dt.date(2026, 1, 1)), _document("b", dt.date(2025, 1, 1)))
    assert len(choose_documents(documents, limit=100)) == 2


def test_documents_with_no_date_come_last_and_are_used_when_dated_ones_run_out():
    documents = _documents(_document("undated"), _document("dated", dt.date(2020, 1, 1)))
    assert _names(choose_documents(documents)) == ["dated", "undated"]
    assert _names(choose_documents(documents, limit=2)) == ["dated", "undated"]
    assert _names(choose_documents(documents, limit=1)) == ["dated"]


def test_same_date_cases_are_ordered_by_spend_id_so_runs_repeat():
    same = dt.date(2026, 1, 1)
    documents = _documents(_document("b", same, spend_id="B"), _document("a", same, spend_id="A"))
    assert _names(choose_documents(documents)) == ["a", "b"]
    assert _names(choose_documents(dict(reversed(documents.items())))) == ["a", "b"]


def test_documents_of_one_case_keep_the_order_the_export_lists_them():
    documents = documents_for_row({**OLD_ROW, "CO_CS_Files": "z.pdf, a.pdf, m.pdf"})
    assert _names(choose_documents(documents)) == ["z.pdf", "a.pdf", "m.pdf"]


def test_choose_documents_does_not_change_its_input():
    documents = _documents(_document("a", dt.date(2025, 1, 1)), _document("b", dt.date(2026, 1, 1)))
    choose_documents(documents, limit=1)
    assert _names(documents) == ["a", "b"]


@pytest.mark.parametrize("limit", [0, -1])
def test_limit_below_one_is_an_error(limit):
    with pytest.raises(ValueError, match="at least 1"):
        choose_documents({}, limit=limit)


def test_no_documents_gives_nothing():
    assert choose_documents({}) == {}


# --- choose_documents: departments ---


def test_departments_are_applied_before_the_limit():
    documents = _documents(
        _document("edu-new", dt.date(2026, 3, 1), department="Department for Education"),
        _document("ho-1", dt.date(2026, 1, 1), department="Home Office"),
        _document("ho-2", dt.date(2025, 6, 1), department="Home Office"),
        _document("ho-3", dt.date(2025, 1, 1), department="Home Office"),
    )
    assert _names(choose_documents(documents, limit=2, departments=["Home Office"])) == ["ho-1", "ho-2"]


def test_an_alb_is_chosen_by_its_parent_department():
    alb_documents = documents_for_row({**OLD_ROW, "CO_OrganisationSubmitter": AN_ALB})
    chosen = choose_documents(alb_documents, departments=[PARENT_MAP[AN_ALB]])
    assert _names(chosen) == ["case.pdf", "annex.docx"]


def test_department_names_match_ignoring_case_and_extra_spaces():
    documents = _documents(_document("a", department="Home Office"))
    assert _names(choose_documents(documents, departments=["  home   OFFICE "])) == ["a"]


def test_several_departments_can_be_asked_for():
    documents = _documents(
        _document("a", dt.date(2026, 1, 1), department="Home Office"),
        _document("b", dt.date(2025, 1, 1), department="HM Treasury"),
        _document("c", dt.date(2024, 1, 1), department="Department for Education"),
    )
    assert _names(choose_documents(documents, departments=["HM Treasury", "Home Office"])) == ["a", "b"]


def test_documents_with_no_department_are_dropped_when_departments_are_given():
    documents = _documents(_document("a", department=None))
    assert choose_documents(documents, departments=["Home Office"]) == {}
    assert _names(choose_documents(documents)) == ["a"]


def test_a_department_that_matches_nothing_gives_nothing():
    documents = _documents(_document("a", department="Home Office"))
    assert choose_documents(documents, departments=["Hom Office"]) == {}


def test_an_empty_department_list_chooses_nothing():
    assert choose_documents(_documents(_document("a")), departments=[]) == {}
