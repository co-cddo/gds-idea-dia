"""Tests for dia.entity_classifications."""

import pytest

from dia.entity_classifications import (
    BASE_ENTITY_CLASSIFICATIONS,
    DOCUMENT_TYPE_ID_FIELDS,
    get_entity_classifications,
)
from dia.types import DocumentType

# --- Base classifications list ---


def test_base_classifications_is_non_empty():
    assert len(BASE_ENTITY_CLASSIFICATIONS) > 0


def test_base_classifications_does_not_contain_id_fields():
    assert "Spend ID" not in BASE_ENTITY_CLASSIFICATIONS
    assert "Contract ID" not in BASE_ENTITY_CLASSIFICATIONS


def test_base_classifications_contains_expected_entries():
    assert "Programme Name" in BASE_ENTITY_CLASSIFICATIONS
    assert "Government Departments" in BASE_ENTITY_CLASSIFICATIONS
    assert "Risk" in BASE_ENTITY_CLASSIFICATIONS


def test_base_classifications_no_duplicates():
    assert len(BASE_ENTITY_CLASSIFICATIONS) == len(set(BASE_ENTITY_CLASSIFICATIONS))


# --- Document type ID fields ---


def test_all_document_types_have_id_field():
    for doc_type in DocumentType:
        assert doc_type in DOCUMENT_TYPE_ID_FIELDS


@pytest.mark.parametrize(
    "document_type,expected_id",
    [
        (DocumentType.BUSINESS_CASE, "Spend ID"),
        (DocumentType.SR_BIDS, "Spend ID"),
        (DocumentType.CONTRACT_FINDER, "Contract ID"),
    ],
)
def test_document_type_id_field(document_type, expected_id):
    assert DOCUMENT_TYPE_ID_FIELDS[document_type] == expected_id


# --- get_entity_classifications ---


@pytest.mark.parametrize(
    "document_type,expected_id,excluded_id",
    [
        (DocumentType.BUSINESS_CASE, "Spend ID", "Contract ID"),
        (DocumentType.SR_BIDS, "Spend ID", "Contract ID"),
        (DocumentType.CONTRACT_FINDER, "Contract ID", "Spend ID"),
    ],
)
def test_get_entity_classifications_includes_correct_id(document_type, expected_id, excluded_id):
    result = get_entity_classifications(document_type)
    assert expected_id in result
    assert excluded_id not in result


def test_get_entity_classifications_includes_all_base():
    result = get_entity_classifications(DocumentType.BUSINESS_CASE)
    for classification in BASE_ENTITY_CLASSIFICATIONS:
        assert classification in result


def test_get_entity_classifications_length():
    result = get_entity_classifications(DocumentType.BUSINESS_CASE)
    assert len(result) == len(BASE_ENTITY_CLASSIFICATIONS) + 1


def test_get_entity_classifications_invalid_type_raises():
    with pytest.raises((KeyError, ValueError)):
        get_entity_classifications("invalid_type")
