"""Tests for dia.metadata.builders — pure lookup-building functions."""

from dia.metadata.builders import (
    build_folder_name_lookup,
    build_gats_lookup,
    build_historic_csv_lookup,
)

# ---------------------------------------------------------------------------
# build_historic_csv_lookup
# ---------------------------------------------------------------------------


def test_historic_lookup_builds_keyed_by_full_path():
    records = [{"filenames": "report.pdf", "department": "Home Office"}]

    lookup = build_historic_csv_lookup(records, prefix="files/")

    assert "files/report.pdf" in lookup
    assert lookup["files/report.pdf"].department == "Home Office"


def test_historic_lookup_includes_all_fields():
    records = [
        {
            "filenames": "report.pdf",
            "department": "Home Office",
            "alb": "National Crime Agency",
            "spend_id": "CS-100",
            "project_name": "Project Alpha",
        }
    ]

    lookup = build_historic_csv_lookup(records, prefix="files/")
    meta = lookup["files/report.pdf"]

    assert meta.department == "Home Office"
    assert meta.alb == "National Crime Agency"
    assert meta.spend_id == "CS-100"
    assert meta.project_name == "Project Alpha"


def test_historic_lookup_tries_alternate_filename_columns():
    records = [{"filename": "report.pdf", "department": "Home Office"}]

    lookup = build_historic_csv_lookup(records, prefix="files/")

    assert "files/report.pdf" in lookup


def test_historic_lookup_skips_rows_without_filename():
    records = [
        {"filenames": "", "department": "Home Office"},
        {"filenames": "report.pdf", "department": "HMRC"},
    ]

    lookup = build_historic_csv_lookup(records, prefix="files/")

    assert len(lookup) == 1
    assert "files/report.pdf" in lookup


def test_historic_lookup_empty_records():
    lookup = build_historic_csv_lookup([], prefix="files/")

    assert lookup == {}


def test_historic_lookup_no_prefix():
    records = [{"filenames": "report.pdf", "department": "Home Office"}]

    lookup = build_historic_csv_lookup(records, prefix="")

    assert "report.pdf" in lookup


# ---------------------------------------------------------------------------
# build_gats_lookup
# ---------------------------------------------------------------------------


def test_gats_lookup_explodes_multiple_files():
    gats_records = [
        {
            "CO_OrganisationSubmitter": "Home Office",
            "CO_SpendID": "CS-100",
            "CO_CS_Files": "a.pdf, b.pdf",
            "CO_CS_CaseName": "Project Alpha",
        }
    ]

    lookup = build_gats_lookup([], gats_records, prefix="files/")

    assert "files/a.pdf" in lookup
    assert "files/b.pdf" in lookup
    assert lookup["files/a.pdf"].spend_id == "CS-100"
    assert lookup["files/b.pdf"].project_name == "Project Alpha"


def test_gats_lookup_maps_submitter_to_department_via_parent_map():
    gats_records = [
        {
            "CO_OrganisationSubmitter": "National Crime Agency",
            "CO_SpendID": "CS-100",
            "CO_CS_Files": "a.pdf",
        }
    ]

    lookup = build_gats_lookup([], gats_records, prefix="files/")

    assert lookup["files/a.pdf"].department == "Home Office"
    assert lookup["files/a.pdf"].alb == "National Crime Agency"


def test_gats_lookup_unmapped_submitter_used_as_department():
    gats_records = [
        {
            "CO_OrganisationSubmitter": "Some Unmapped Org",
            "CO_SpendID": "CS-100",
            "CO_CS_Files": "a.pdf",
        }
    ]

    lookup = build_gats_lookup([], gats_records, prefix="files/")

    assert lookup["files/a.pdf"].department == "Some Unmapped Org"


def test_gats_lookup_overrides_historic_for_same_filename():
    historic_records = [{"filenames": "a.pdf", "department": "Old Department"}]
    gats_records = [
        {
            "CO_OrganisationSubmitter": "Home Office",
            "CO_SpendID": "CS-100",
            "CO_CS_Files": "a.pdf",
        }
    ]

    lookup = build_gats_lookup(historic_records, gats_records, prefix="files/")

    assert lookup["files/a.pdf"].department == "Home Office"
    assert lookup["files/a.pdf"].spend_id == "CS-100"


def test_gats_lookup_combines_with_historic_for_different_filenames():
    historic_records = [{"filenames": "legacy.pdf", "department": "DWP"}]
    gats_records = [
        {
            "CO_OrganisationSubmitter": "Home Office",
            "CO_SpendID": "CS-100",
            "CO_CS_Files": "new.pdf",
        }
    ]

    lookup = build_gats_lookup(historic_records, gats_records, prefix="files/")

    assert "files/legacy.pdf" in lookup
    assert "files/new.pdf" in lookup
    assert lookup["files/legacy.pdf"].department == "DWP"
    assert lookup["files/new.pdf"].department == "Home Office"


def test_gats_lookup_skips_rows_without_files():
    gats_records = [
        {"CO_OrganisationSubmitter": "Home Office", "CO_SpendID": "CS-100", "CO_CS_Files": ""},
    ]

    lookup = build_gats_lookup([], gats_records, prefix="files/")

    assert lookup == {}


def test_gats_lookup_strips_whitespace_in_file_list():
    gats_records = [
        {
            "CO_OrganisationSubmitter": "Home Office",
            "CO_SpendID": "CS-100",
            "CO_CS_Files": " a.pdf ,  b.pdf  ",
        }
    ]

    lookup = build_gats_lookup([], gats_records, prefix="files/")

    assert "files/a.pdf" in lookup
    assert "files/b.pdf" in lookup


def test_gats_lookup_captures_assurance_date():
    gats_records = [
        {
            "CO_OrganisationSubmitter": "Home Office",
            "CO_CS_Files": "a.pdf",
            "CO_AssuranceRatingRequestedDate": "2023-01-01",
        }
    ]

    lookup = build_gats_lookup([], gats_records, prefix="files/")

    assert lookup["files/a.pdf"].assurance_date == "2023-01-01"


def test_gats_lookup_empty_inputs():
    lookup = build_gats_lookup([], [], prefix="files/")

    assert lookup == {}


# ---------------------------------------------------------------------------
# build_folder_name_lookup
# ---------------------------------------------------------------------------


def test_folder_name_lookup_derives_department_from_folder():
    keys = ["sr21-bids/Home Office/Project Alpha.docx"]

    lookup = build_folder_name_lookup(keys, prefix="sr21-bids/")

    meta = lookup["sr21-bids/Home Office/Project Alpha.docx"]
    assert meta.department == "Home Office"
    assert meta.project_name == "Project Alpha"


def test_folder_name_lookup_maps_folder_via_parent_map():
    keys = ["sr21-bids/HMRC/report.pdf"]

    lookup = build_folder_name_lookup(keys, prefix="sr21-bids/")

    meta = lookup["sr21-bids/HMRC/report.pdf"]
    assert meta.department == "HM Revenue and Customs"
    assert meta.alb == "HMRC"


def test_folder_name_lookup_no_alb_when_folder_is_canonical():
    keys = ["sr21-bids/Home Office/report.pdf"]

    lookup = build_folder_name_lookup(keys, prefix="sr21-bids/")

    meta = lookup["sr21-bids/Home Office/report.pdf"]
    assert meta.department == "Home Office"
    assert meta.alb is None


def test_folder_name_lookup_skips_keys_with_no_folder():
    keys = ["sr21-bids/report.pdf"]

    lookup = build_folder_name_lookup(keys, prefix="sr21-bids/")

    assert lookup == {}


def test_folder_name_lookup_handles_no_prefix_match():
    keys = ["Home Office/report.pdf"]

    lookup = build_folder_name_lookup(keys, prefix="")

    meta = lookup["Home Office/report.pdf"]
    assert meta.department == "Home Office"


def test_folder_name_lookup_empty_keys():
    lookup = build_folder_name_lookup([], prefix="sr21-bids/")

    assert lookup == {}


def test_folder_name_lookup_strips_extension_for_project_name():
    keys = ["prefix/Dept/My Project Name.pdf"]

    lookup = build_folder_name_lookup(keys, prefix="prefix/")

    assert lookup["prefix/Dept/My Project Name.pdf"].project_name == "My Project Name"
