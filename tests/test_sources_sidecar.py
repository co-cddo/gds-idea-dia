"""Tests for dia.sources.sidecar: the metadata file written next to every document."""

import json

import pytest

from dia.document_types import DocumentType
from dia.sources.definitions import SOURCES
from dia.sources.sidecar import Sidecar, SidecarError, check, from_json, sidecar_key, to_json


def _attributes(text: str) -> dict:
    return json.loads(text)["metadataAttributes"]


# --- sidecar_key ---


def test_sidecar_key_goes_next_to_the_document():
    assert sidecar_key("files/case-123.pdf") == "files/case-123.pdf.metadata.json"


def test_sidecar_key_keeps_spaces_and_nested_folders():
    key = "readouts/20260901 Letter to HMRC - Digital Business Review 010926.pdf"
    assert sidecar_key(key) == key + ".metadata.json"


def test_sidecar_key_rejects_an_empty_key():
    with pytest.raises(SidecarError):
        sidecar_key("")


def test_sidecar_key_rejects_a_sidecar_key():
    with pytest.raises(SidecarError, match="already a sidecar"):
        sidecar_key("files/case-123.pdf.metadata.json")


# --- Sidecar ---


def test_only_document_type_is_required():
    sidecar = Sidecar(document_type=DocumentType.BUSINESS_CASE)
    assert sidecar.department_name is None


def test_document_type_is_required():
    with pytest.raises(ValueError):
        Sidecar()  # type: ignore[call-arg]


def test_unknown_field_is_rejected():
    with pytest.raises(ValueError):
        Sidecar(document_type=DocumentType.BUSINESS_CASE, departmnet_name="DfE")  # type: ignore[call-arg]


def test_year_must_be_a_number_not_text():
    with pytest.raises(ValueError):
        Sidecar(document_type=DocumentType.BUSINESS_CASE, year="2025")  # type: ignore[arg-type]


def test_assurance_date_is_text():
    assert Sidecar(document_type=DocumentType.BUSINESS_CASE, assurance_date="2025-03-01").assurance_date == "2025-03-01"
    with pytest.raises(ValueError):
        Sidecar(document_type=DocumentType.BUSINESS_CASE, assurance_date=20250301)  # type: ignore[arg-type]


def test_is_latest_must_be_a_real_boolean():
    with pytest.raises(ValueError):
        Sidecar(document_type=DocumentType.DBR_READOUT, is_latest="true")  # type: ignore[arg-type]


# --- to_json / from_json ---


def test_to_json_uses_bedrocks_wrapper_and_leaves_out_unset_fields():
    text = to_json(Sidecar(document_type=DocumentType.BUSINESS_CASE, department_name="DfE"))
    assert json.loads(text) == {"metadataAttributes": {"document_type": "business_case", "department_name": "DfE"}}


def test_to_json_keeps_numbers_and_booleans_as_numbers_and_booleans():
    sidecar = Sidecar(
        document_type=DocumentType.DBR_READOUT,
        year=2026,
        date=20260901,
        is_latest=True,
    )
    attributes = _attributes(to_json(sidecar))
    assert attributes["year"] == 2026
    assert attributes["date"] == 20260901
    assert attributes["is_latest"] is True


def test_round_trip_gives_the_same_sidecar():
    sidecar = Sidecar(
        document_type=DocumentType.BUSINESS_CASE,
        department_name="Department for Education",
        alb="Ofqual",
        year=2025,
        spend_id="COSC-03416",
        project_name="School Data Platform",
        assurance_date="2025-03-01",
    )
    assert from_json(to_json(sidecar)) == sidecar


def test_false_is_written_not_dropped():
    sidecar = Sidecar(document_type=DocumentType.DBR_READOUT, is_latest=False)
    assert _attributes(to_json(sidecar))["is_latest"] is False


def test_from_json_rejects_text_that_is_not_json():
    with pytest.raises(SidecarError, match="not valid JSON"):
        from_json("{nope")


@pytest.mark.parametrize(
    "text",
    [
        "[]",
        "{}",
        '{"metadataAttributes": []}',
        '{"document_type": "business_case"}',
        '{"metadataAttributes": {"document_type": "business_case"}, "other": 1}',
    ],
)
def test_from_json_rejects_the_wrong_shape(text):
    with pytest.raises(SidecarError, match="metadataAttributes"):
        from_json(text)


def test_from_json_rejects_an_unknown_key():
    text = json.dumps({"metadataAttributes": {"document_type": "business_case", "colour": "red"}})
    with pytest.raises(SidecarError, match="invalid metadata"):
        from_json(text)


def test_from_json_rejects_a_year_written_as_text():
    text = json.dumps({"metadataAttributes": {"document_type": "business_case", "year": "2025"}})
    with pytest.raises(SidecarError, match="invalid metadata"):
        from_json(text)


def test_from_json_rejects_an_unknown_document_type():
    text = json.dumps({"metadataAttributes": {"document_type": "sr_bid"}})
    with pytest.raises(SidecarError, match="invalid metadata"):
        from_json(text)


def test_from_json_rejects_a_missing_document_type():
    text = json.dumps({"metadataAttributes": {"year": 2025}})
    with pytest.raises(SidecarError, match="invalid metadata"):
        from_json(text)


# --- check ---


def test_check_accepts_a_sidecar_that_fits_its_source():
    sidecar = Sidecar(
        document_type=DocumentType.BUSINESS_CASE,
        department_name="DfE",
        spend_id="COSC-03416",
        assurance_date="2025-03-01",
    )
    check(sidecar, SOURCES["gats_business_cases"])


def test_check_rejects_another_sources_document_type():
    sidecar = Sidecar(document_type=DocumentType.SR_BIDS_2025)
    with pytest.raises(SidecarError, match="document_type"):
        check(sidecar, SOURCES["gats_business_cases"])


def test_check_rejects_a_key_the_source_does_not_declare():
    sidecar = Sidecar(document_type=DocumentType.BUSINESS_CASE, is_latest=True)
    with pytest.raises(SidecarError, match="is_latest"):
        check(sidecar, SOURCES["gats_business_cases"])


def test_check_lists_every_key_that_is_not_allowed():
    sidecar = Sidecar(document_type=DocumentType.NAO_REPORT, spend_id="X", is_latest=True)
    with pytest.raises(SidecarError, match="is_latest, spend_id"):
        check(sidecar, SOURCES["nao_reports"])


def test_check_allows_a_source_s_own_extra_keys():
    sidecar = Sidecar(document_type=DocumentType.DBR_READOUT, date=20260901, is_latest=True)
    check(sidecar, SOURCES["dbr_readouts_letter"])


@pytest.mark.parametrize("name", SOURCES)
def test_every_source_accepts_a_date(name):
    source = SOURCES[name]
    check(Sidecar(document_type=source.document_type, date=20260901), source)


# --- the model and the declarations agree ---


def test_every_declared_key_is_a_sidecar_field():
    declared = {key for source in SOURCES.values() for key in source.metadata_keys}
    assert declared <= set(Sidecar.model_fields)


def test_every_sidecar_field_is_declared_by_some_source():
    declared = {key for source in SOURCES.values() for key in source.metadata_keys}
    # document_type is always set from the source, so it is in the common keys too.
    assert set(Sidecar.model_fields) <= declared


@pytest.mark.parametrize("name", SOURCES)
def test_a_sidecar_with_every_allowed_key_passes_check(name):
    source = SOURCES[name]
    values = {
        "document_type": source.document_type,
        "year": 2025,
        "date": 20260901,
        "is_latest": True,
    }
    allowed = {key: values.get(key, "x") for key in source.metadata_keys}
    check(Sidecar(**allowed), source)
