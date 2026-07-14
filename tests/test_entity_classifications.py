"""Tests for dia.entity_classifications."""

import pytest

from dia.entity_classifications import (
    BASE_ENTITY_CLASSIFICATIONS,
    DOCUMENT_TYPE_ID_FIELDS,
    get_entity_classifications,
)
from dia.types import DocumentType


class TestBaseEntityClassifications:
    """Test the base classifications list."""

    def test_is_non_empty(self):
        assert len(BASE_ENTITY_CLASSIFICATIONS) > 0

    def test_does_not_contain_spend_id(self):
        assert "Spend ID" not in BASE_ENTITY_CLASSIFICATIONS

    def test_does_not_contain_contract_id(self):
        assert "Contract ID" not in BASE_ENTITY_CLASSIFICATIONS

    def test_contains_expected_entries(self):
        assert "Programme Name" in BASE_ENTITY_CLASSIFICATIONS
        assert "Government Departments" in BASE_ENTITY_CLASSIFICATIONS
        assert "Risk" in BASE_ENTITY_CLASSIFICATIONS

    def test_no_duplicates(self):
        assert len(BASE_ENTITY_CLASSIFICATIONS) == len(set(BASE_ENTITY_CLASSIFICATIONS))


class TestDocumentTypeIdFields:
    """Test the ID field mapping."""

    def test_all_document_types_have_id_field(self):
        for doc_type in DocumentType:
            assert doc_type in DOCUMENT_TYPE_ID_FIELDS

    def test_business_case_uses_spend_id(self):
        assert DOCUMENT_TYPE_ID_FIELDS[DocumentType.BUSINESS_CASE] == "Spend ID"

    def test_sr_bids_uses_spend_id(self):
        assert DOCUMENT_TYPE_ID_FIELDS[DocumentType.SR_BIDS] == "Spend ID"

    def test_contract_finder_uses_contract_id(self):
        assert DOCUMENT_TYPE_ID_FIELDS[DocumentType.CONTRACT_FINDER] == "Contract ID"


class TestGetEntityClassifications:
    """Test the get_entity_classifications function."""

    def test_business_case_includes_spend_id(self):
        result = get_entity_classifications(DocumentType.BUSINESS_CASE)
        assert "Spend ID" in result
        assert "Contract ID" not in result

    def test_sr_bids_includes_spend_id(self):
        result = get_entity_classifications(DocumentType.SR_BIDS)
        assert "Spend ID" in result
        assert "Contract ID" not in result

    def test_contract_finder_includes_contract_id(self):
        result = get_entity_classifications(DocumentType.CONTRACT_FINDER)
        assert "Contract ID" in result
        assert "Spend ID" not in result

    def test_includes_all_base_classifications(self):
        result = get_entity_classifications(DocumentType.BUSINESS_CASE)
        for classification in BASE_ENTITY_CLASSIFICATIONS:
            assert classification in result

    def test_result_length(self):
        result = get_entity_classifications(DocumentType.BUSINESS_CASE)
        assert len(result) == len(BASE_ENTITY_CLASSIFICATIONS) + 1

    def test_invalid_document_type_raises(self):
        with pytest.raises((KeyError, ValueError)):
            get_entity_classifications("invalid_type")
