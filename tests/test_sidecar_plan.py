"""Tests for dia.sources.sidecar_plan: what an export would label, given the bucket."""

import pytest

from dia.sources.sidecar_plan import plan

PREFIX = "files/"


def _row(spend_id, files, submitter="Home Office", date="2026-05-01"):
    return {
        "CO_SpendID": spend_id,
        "CO_OrganisationSubmitter": submitter,
        "CO_CaseSubmitDate": date,
        "CO_CS_Files": files,
    }


def _plan(rows, bucket_keys=(), **kwargs):
    return plan(rows, bucket_keys, prefix=PREFIX, **kwargs)


# --- counts that come from the export alone ---


def test_rows_are_counted_and_rows_with_no_files_are_counted_separately():
    result = _plan([_row("S1", "a.pdf"), _row("S2", ""), _row("S3", "b.pdf")])
    assert result.rows_read == 3
    assert result.rows_without_documents == 1


def test_a_file_listed_by_two_rows_is_one_document_and_the_later_row_wins():
    result = _plan(
        [_row("S1", "a.pdf", date="2026-01-01"), _row("S2", "a.pdf", date="2026-06-01")],
        ["files/a.pdf"],
    )
    assert result.listed == 1
    assert result.new["files/a.pdf.metadata.json"].spend_id == "S2"


def test_documents_with_no_date_are_counted_among_everything_listed():
    result = _plan([_row("S1", "a.pdf", date=""), _row("S2", "b.pdf", date="not a date"), _row("S3", "c.pdf")])
    assert result.listed == 3
    assert result.listed_without_date == 2


def test_unrecognised_submitters_are_counted_by_name_in_rows():
    rows = [
        _row("S1", "a.pdf", submitter="Cabinet Ofice"),
        _row("S2", "b.pdf", submitter="Cabinet Ofice"),
        _row("S3", "", submitter="Nowhere Agency"),
        _row("S4", "c.pdf", submitter="Home Office"),
    ]
    assert _plan(rows).unrecognised_submitters == {"Cabinet Ofice": 2, "Nowhere Agency": 1}


def test_departments_that_match_nothing_are_reported_before_the_limit_is_applied():
    rows = [_row("S1", "a.pdf"), _row("S2", "b.pdf")]
    result = _plan(rows, departments=["Home Office", "Nowhere Office"], limit=1)
    assert result.unmatched_departments == ["Nowhere Office"]


def test_no_departments_asked_for_means_none_unmatched():
    assert _plan([_row("S1", "a.pdf")]).unmatched_departments == []


# --- choosing, and comparing with the bucket ---


def test_the_limit_counts_documents_and_takes_the_newest():
    rows = [
        _row("S1", "old.pdf", date="2026-01-01"),
        _row("S2", "mid.pdf", date="2026-03-01"),
        _row("S3", "new.pdf", date="2026-05-01"),
    ]
    bucket = [f"files/{name}" for name in ("old.pdf", "mid.pdf", "new.pdf")]
    result = _plan(rows, bucket, limit=2)
    assert result.listed == 3
    assert result.chosen == 2
    assert list(result.new) == ["files/new.pdf.metadata.json", "files/mid.pdf.metadata.json"]


def test_a_chosen_file_that_is_not_in_the_bucket_is_counted_and_not_written():
    result = _plan([_row("S1", "a.pdf, ghost.pdf")], ["files/a.pdf"])
    assert result.chosen == 2
    assert result.chosen_not_in_bucket == 1
    assert list(result.new) == ["files/a.pdf.metadata.json"]


def test_a_file_with_no_label_is_new_and_one_with_a_label_is_a_replacement():
    result = _plan([_row("S1", "a.pdf, b.docx")], ["files/a.pdf", "files/b.docx", "files/a.pdf.metadata.json"])
    assert list(result.new) == ["files/b.docx.metadata.json"]
    assert list(result.replacements) == ["files/a.pdf.metadata.json"]
    assert result.chosen_already_labelled == 1
    assert result.would_write_new == 1
    assert result.would_write_with_overwrite == 2


def test_the_sidecars_to_write_hold_the_mapped_metadata():
    sidecar = _plan([_row("S1", "a.pdf")], ["files/a.pdf"]).new["files/a.pdf.metadata.json"]
    assert (sidecar.spend_id, sidecar.department_name, str(sidecar.date)) == ("S1", "Home Office", "2026-05-01")


# --- the bucket side ---


def test_bucket_documents_the_export_does_not_list_are_counted():
    result = _plan([_row("S1", "a.pdf")], ["files/a.pdf", "files/z.pdf", "files/y.docx"])
    assert result.bucket_not_listed == 2


def test_the_limit_does_not_make_listed_documents_look_unlisted():
    rows = [_row("S1", "a.pdf", date="2026-01-01"), _row("S2", "b.pdf", date="2026-05-01")]
    result = _plan(rows, ["files/a.pdf", "files/b.pdf"], limit=1)
    assert result.bucket_not_listed == 0


def test_json_files_in_the_bucket_are_not_documents():
    result = _plan([_row("S1", "a.pdf")], ["files/a.pdf", "files/old.json", "files/OTHER.JSON"])
    assert result.bucket_not_listed == 0


def test_a_listed_json_file_is_not_found_in_the_bucket():
    result = _plan([_row("S1", "a.pdf, extra.json")], ["files/a.pdf", "files/extra.json"])
    assert result.chosen_not_in_bucket == 1
    assert list(result.new) == ["files/a.pdf.metadata.json"]


def test_a_listed_name_that_looks_like_a_sidecar_does_not_crash_the_plan():
    result = _plan([_row("S1", "a.pdf.metadata.json")], ["files/a.pdf.metadata.json"])
    assert result.chosen_not_in_bucket == 1
    assert result.new == {}


def test_files_outside_the_prefix_do_not_match():
    result = _plan([_row("S1", "a.pdf")], ["other/a.pdf"])
    assert result.chosen_not_in_bucket == 1


def test_an_empty_export_and_an_empty_bucket_give_zeros():
    result = _plan([])
    assert (result.rows_read, result.listed, result.chosen, result.would_write_with_overwrite) == (0, 0, 0, 0)


def test_a_limit_below_one_is_rejected():
    with pytest.raises(ValueError, match="at least 1"):
        _plan([_row("S1", "a.pdf")], limit=0)


# --- dates that could not be read ---


def test_unreadable_dates_are_counted_by_text_in_rows_that_list_files():
    rows = [
        _row("S1", "a.pdf", date="soon"),
        _row("S2", "b.pdf", date="soon"),
        _row("S3", "c.pdf", date="01/03/2025"),
        _row("S4", "d.pdf", date="30-Mar-26"),
    ]
    assert _plan(rows).unreadable_dates == {"soon": 2, "01/03/2025": 1}


def test_an_empty_date_is_not_unreadable_but_is_still_a_document_with_no_date():
    result = _plan([_row("S1", "a.pdf", date="")])
    assert result.unreadable_dates == {}
    assert result.listed_without_date == 1


def test_an_unreadable_date_on_a_row_with_no_files_is_not_counted():
    assert _plan([_row("S1", "", date="soon")]).unreadable_dates == {}


def test_documents_with_an_unreadable_date_are_still_listed_and_chosen():
    result = _plan([_row("S1", "a.pdf", date="soon")], ["files/a.pdf"])
    assert (result.listed, result.listed_without_date, result.chosen) == (1, 1, 1)


# --- test data ---


def test_rows_from_test_submitters_are_ignored_and_counted():
    rows = [
        _row("S1", "a.pdf"),
        _row("S2", "b.pdf", submitter="GATS_test"),
        _row("S3", "c.pdf", submitter="00_Test"),
        _row("S4", "", submitter="GATS_test"),
    ]
    result = _plan(rows, ["files/a.pdf", "files/b.pdf", "files/c.pdf"])

    assert (result.rows_read, result.test_rows_ignored) == (4, 3)
    assert result.listed == 1
    assert list(result.new) == ["files/a.pdf.metadata.json"]


def test_ignored_test_rows_are_in_no_other_row_count():
    rows = [_row("S1", "a.pdf", submitter="GATS_test", date="soon"), _row("S2", "", submitter="00_Test")]
    result = _plan(rows)

    assert result.rows_without_documents == 0
    assert result.unrecognised_submitters == {}
    assert result.unreadable_dates == {}


def test_a_test_documents_file_counts_as_not_listed_by_the_export():
    result = _plan([_row("S1", "a.pdf", submitter="GATS_test")], ["files/a.pdf"])
    assert result.bucket_not_listed == 1
