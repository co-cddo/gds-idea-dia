"""Tests for dia.sources.sidecar_plan: what an export would label, given the bucket."""

import json

import pytest

from dia.sources.sidecar import Sidecar, to_json
from dia.sources.sidecar_plan import Outcome, plan

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


def test_a_replacement_keeps_the_exact_text_of_the_label_it_replaces():
    old = '{"metadataAttributes": {"department": "Home Office"}}  '
    result = _plan(
        [_row("S1", "a.pdf")],
        ["files/a.pdf", "files/a.pdf.metadata.json"],
        read_labels=lambda keys: {key: old for key in keys},
    )
    assert result.replaced_text == {"files/a.pdf.metadata.json": old}


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
    assert result.outcomes["files/a.pdf"] is Outcome.FROM_EXPORT
    assert result.outcomes["files/b.pdf"] is Outcome.BASIC_LABEL
    assert result.outcomes["files/c.pdf"] is Outcome.BASIC_LABEL


def test_ignored_test_rows_are_in_no_other_row_count():
    rows = [_row("S1", "a.pdf", submitter="GATS_test", date="soon"), _row("S2", "", submitter="00_Test")]
    result = _plan(rows)

    assert result.rows_without_documents == 0
    assert result.unrecognised_submitters == {}
    assert result.unreadable_dates == {}


# --- what every document in the bucket gets ---

HOME_OFFICE = "Home Office"


def _old_label(**attributes):
    return json.dumps({"metadataAttributes": {"document_type": "business_case", **attributes}})


def _reader(labels):
    """A `read_labels` that serves the given `{label key: text}` and records what it was asked for."""
    asked = []

    def read(keys):
        asked.append(list(keys))
        return {key: labels[key] for key in keys if key in labels}

    read.asked = asked
    return read


def _full(rows, bucket, labels=None, **kwargs):
    """Plan with the labels given as `{label key: text}`. Their keys are in the bucket, as in a real listing."""
    labels = labels or {}
    keys = list(dict.fromkeys([*bucket, *labels]))
    return plan(rows, keys, prefix=PREFIX, read_labels=_reader(labels), **kwargs)


def test_a_document_no_export_lists_with_no_label_gets_a_basic_label_if_it_is_a_pdf_or_word_file():
    result = _full([], ["files/a.pdf", "files/b.docx", "files/c.PDF"])

    assert {key: result.outcomes[key] for key in sorted(result.outcomes)} == {
        "files/a.pdf": Outcome.BASIC_LABEL,
        "files/b.docx": Outcome.BASIC_LABEL,
        "files/c.PDF": Outcome.BASIC_LABEL,
    }
    assert set(result.new) == {f"files/{name}.metadata.json" for name in ("a.pdf", "b.docx", "c.PDF")}
    assert all(sidecar == Sidecar(document_type="business_case") for sidecar in result.new.values())


@pytest.mark.parametrize("name", ["a.pptx", "c.png", "h"])
def test_a_document_of_any_other_type_with_nothing_to_label_it_from_waits(name):
    result = _full([], [f"files/{name}"])
    assert result.outcomes == {f"files/{name}": Outcome.WAITING}
    assert result.new == {}
    assert result.count(Outcome.WAITING) == 1


def test_a_document_an_export_lists_is_labelled_whatever_its_type():
    result = _full([_row("S1", "slides.pptx")], ["files/slides.pptx"])
    assert result.outcomes == {"files/slides.pptx": Outcome.FROM_EXPORT}
    assert list(result.new) == ["files/slides.pptx.metadata.json"]


def test_a_document_no_export_lists_is_rebuilt_from_the_case_its_old_label_names():
    rows = [_row("S1", "listed.pdf", date="2026-05-01"), _row("S1", "", date="2026-05-01")]
    old = _old_label(spend_id="S1", department="Old Name", file_reference=3)
    result = _full(rows, ["files/listed.pdf", "files/other.pdf"], {"files/other.pdf.metadata.json": old})

    assert result.outcomes["files/other.pdf"] is Outcome.REBUILT_FROM_CASE
    rebuilt = result.replacements["files/other.pdf.metadata.json"]
    assert (rebuilt.spend_id, rebuilt.department_name, str(rebuilt.date)) == ("S1", HOME_OFFICE, "2026-05-01")


def test_a_case_whose_row_lists_no_files_still_rebuilds_labels_by_spend_id():
    result = _full([_row("S1", "")], ["files/x.pdf"], {"files/x.pdf.metadata.json": _old_label(spend_id="S1")})
    assert result.outcomes == {"files/x.pdf": Outcome.REBUILT_FROM_CASE}


def test_the_later_row_for_a_case_is_the_one_a_document_is_rebuilt_from():
    rows = [_row("S1", "", date="2025-01-01"), _row("S1", "", date="2026-06-01")]
    result = _full(rows, ["files/x.pdf"], {"files/x.pdf.metadata.json": _old_label(spend_id="S1")})
    assert str(result.replacements["files/x.pdf.metadata.json"].date) == "2026-06-01"


def test_a_case_from_a_test_row_is_not_used_to_rebuild_a_label():
    rows = [_row("S1", "a.pdf", submitter="GATS_test")]
    result = _full(rows, ["files/x.pdf"], {"files/x.pdf.metadata.json": _old_label(spend_id="S1")})
    assert result.outcomes["files/x.pdf"] is Outcome.OLD_LABEL_KEPT


def test_an_old_label_whose_case_is_not_in_the_exports_is_kept_when_it_is_already_valid():
    old = _old_label(spend_id="S9")
    result = _full([], ["files/x.pdf"], {"files/x.pdf.metadata.json": old})

    assert result.outcomes == {"files/x.pdf": Outcome.OLD_LABEL_KEPT}
    assert (result.new, result.replacements, result.unchanged) == ({}, {}, 1)


def test_an_old_label_in_the_old_scripts_format_is_fixed_when_its_case_is_not_in_the_exports():
    old = _old_label(spend_id="S9", department=HOME_OFFICE, file_reference=7)
    result = _full([], ["files/x.pdf"], {"files/x.pdf.metadata.json": old})

    assert result.outcomes == {"files/x.pdf": Outcome.OLD_LABEL_FIXED}
    fixed = result.replacements["files/x.pdf.metadata.json"]
    assert (fixed.spend_id, fixed.department_name) == ("S9", HOME_OFFICE)


@pytest.mark.parametrize(
    "text", ["not json", _old_label(year=2024), json.dumps({"metadataAttributes": {"spend_id": "S1"}})]
)
def test_an_old_label_that_cannot_be_fixed_is_left_alone_and_counted(text):
    result = _full([], ["files/x.pdf"], {"files/x.pdf.metadata.json": text})

    assert result.outcomes == {"files/x.pdf": Outcome.OLD_LABEL_UNFIXABLE}
    assert (result.new, result.replacements) == ({}, {})


def test_the_export_wins_over_the_old_label_for_a_document_it_lists():
    old = _old_label(spend_id="S9", department="Other")
    result = _full([_row("S1", "a.pdf")], ["files/a.pdf"], {"files/a.pdf.metadata.json": old})

    assert result.outcomes == {"files/a.pdf": Outcome.FROM_EXPORT}
    assert result.replacements["files/a.pdf.metadata.json"].spend_id == "S1"


# --- compare before replacing ---


def test_a_label_that_already_holds_what_the_document_would_get_is_not_written_again():
    rows = [_row("S1", "a.pdf", date="2026-05-01")]
    first = _full(rows, ["files/a.pdf"])
    existing = to_json(first.new["files/a.pdf.metadata.json"])

    again = _full(rows, ["files/a.pdf", "files/a.pdf.metadata.json"], {"files/a.pdf.metadata.json": existing})

    assert (again.new, again.replacements, again.unchanged) == ({}, {}, 1)
    assert (again.would_write_new, again.would_write_with_overwrite) == (0, 0)


def test_a_label_that_differs_is_a_replacement_and_a_missing_one_is_new():
    rows = [_row("S1", "a.pdf", date="2026-05-01"), _row("S2", "b.pdf", date="2026-05-01")]
    stale = to_json(_full([_row("S1", "a.pdf", date="2025-01-01")], ["files/a.pdf"]).new["files/a.pdf.metadata.json"])

    result = _full(rows, ["files/a.pdf", "files/b.pdf"], {"files/a.pdf.metadata.json": stale})

    assert list(result.new) == ["files/b.pdf.metadata.json"]
    assert list(result.replacements) == ["files/a.pdf.metadata.json"]
    assert (result.would_write_new, result.would_write_with_overwrite) == (1, 2)


def test_a_minimal_label_is_replaced_once_an_export_lists_the_document():
    minimal = to_json(Sidecar(document_type="business_case"))
    result = _full([_row("S1", "a.pdf")], ["files/a.pdf"], {"files/a.pdf.metadata.json": minimal})
    assert list(result.replacements) == ["files/a.pdf.metadata.json"]


def test_a_run_over_the_whole_bucket_reads_every_existing_label_once():
    reader = _reader({})
    plan(
        [_row("S1", "a.pdf")],
        ["files/a.pdf", "files/b.pdf", "files/a.pdf.metadata.json", "files/b.pdf.metadata.json"],
        prefix=PREFIX,
        read_labels=reader,
    )
    assert reader.asked == [["files/a.pdf.metadata.json", "files/b.pdf.metadata.json"]]


# --- a limit or departments: only the chosen files are in the run ---


def test_with_a_limit_only_the_chosen_files_are_labelled_and_the_rest_are_left_alone():
    rows = [_row("S1", "old.pdf", date="2025-01-01"), _row("S2", "new.pdf", date="2026-05-01")]
    bucket = ["files/old.pdf", "files/new.pdf", "files/unlisted.pdf", "files/slides.pptx"]
    result = _full(rows, bucket, limit=1)

    assert result.outcomes == {"files/new.pdf": Outcome.FROM_EXPORT}
    assert list(result.new) == ["files/new.pdf.metadata.json"]
    assert result.outside_run == 3


def test_with_departments_only_labels_of_the_chosen_files_are_read():
    rows = [_row("S1", "a.pdf"), _row("S2", "b.pdf", submitter="HM Treasury")]
    bucket = ["files/a.pdf", "files/b.pdf", "files/a.pdf.metadata.json", "files/b.pdf.metadata.json", "files/c.pdf"]
    reader = _reader({})

    result = plan(rows, bucket, prefix=PREFIX, read_labels=reader, departments=[HOME_OFFICE])

    assert reader.asked == [["files/a.pdf.metadata.json"]]
    assert list(result.outcomes) == ["files/a.pdf"]
    assert result.outside_run == 2


# --- rows from several exports ---


def test_rows_from_several_exports_are_combined_and_the_later_one_wins_for_a_shared_file():
    older = [_row("S1", "shared.pdf", date="2025-01-01"), _row("S2", "only-old.pdf", date="2025-02-01")]
    newer = [_row("S3", "shared.pdf", date="2026-06-01"), _row("S4", "only-new.pdf", date="2026-07-01")]
    result = _full(older + newer, ["files/shared.pdf", "files/only-old.pdf", "files/only-new.pdf"])

    assert result.listed == 3
    assert result.new["files/shared.pdf.metadata.json"].spend_id == "S3"
    assert {s.spend_id for s in result.new.values()} == {"S3", "S2", "S4"}


# --- the totals add up ---
