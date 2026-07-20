"""Tests for dia.document_types — DocumentType, config, and entity classifications."""

import pytest

from dia.config import ChunkingConfig
from dia.document_types import (
    _CONFIGS,
    BASE_ENTITY_CLASSIFICATIONS,
    DocumentType,
    DocumentTypeConfig,
)

# --- DocumentType enum ---


def test_document_type_values():
    assert DocumentType.BUSINESS_CASE == "business_case"
    assert DocumentType.SR_BIDS == "sr_bids"
    assert DocumentType.CONTRACT_FINDER == "contract_finder"


# --- Completeness validation ---


def test_all_document_types_have_config():
    """Every DocumentType value must have an entry in _CONFIGS."""
    for doc_type in DocumentType:
        assert doc_type in _CONFIGS, f"Missing config for {doc_type}"


# --- DocumentType.config property ---


def test_business_case_config():
    config = DocumentType.BUSINESS_CASE.config
    assert isinstance(config, DocumentTypeConfig)
    assert config.id_field == "Spend ID"


def test_contract_finder_config():
    config = DocumentType.CONTRACT_FINDER.config
    assert config.id_field == "Contract ID"
    assert config.chunking.use_semantic_splitting is False


# --- DocumentType.entity_classifications property ---


def test_entity_classifications_includes_base():
    result = DocumentType.BUSINESS_CASE.entity_classifications
    for classification in BASE_ENTITY_CLASSIFICATIONS:
        assert classification in result


def test_entity_classifications_includes_id_field():
    assert "Spend ID" in DocumentType.BUSINESS_CASE.entity_classifications
    assert "Spend ID" in DocumentType.SR_BIDS.entity_classifications
    assert "Contract ID" in DocumentType.CONTRACT_FINDER.entity_classifications


def test_entity_classifications_excludes_wrong_id():
    assert "Contract ID" not in DocumentType.BUSINESS_CASE.entity_classifications
    assert "Spend ID" not in DocumentType.CONTRACT_FINDER.entity_classifications


def test_entity_classifications_length():
    result = DocumentType.BUSINESS_CASE.entity_classifications
    assert len(result) == len(BASE_ENTITY_CLASSIFICATIONS) + 1


# --- DocumentType.chunking property ---


def test_business_case_uses_full_chunking():
    chunking = DocumentType.BUSINESS_CASE.chunking
    assert chunking.use_semantic_splitting is True
    assert chunking.sentence_chunk_size == 7900


def test_sr_bids_uses_full_chunking():
    chunking = DocumentType.SR_BIDS.chunking
    assert chunking.use_semantic_splitting is True


def test_contract_finder_skips_semantic_splitting():
    chunking = DocumentType.CONTRACT_FINDER.chunking
    assert chunking.use_semantic_splitting is False
    assert chunking.sentence_chunk_size == 7900


# --- Base classifications list ---


def test_base_classifications_is_non_empty():
    assert len(BASE_ENTITY_CLASSIFICATIONS) > 0


def test_base_classifications_no_duplicates():
    assert len(BASE_ENTITY_CLASSIFICATIONS) == len(set(BASE_ENTITY_CLASSIFICATIONS))


def test_base_classifications_does_not_contain_id_fields():
    assert "Spend ID" not in BASE_ENTITY_CLASSIFICATIONS
    assert "Contract ID" not in BASE_ENTITY_CLASSIFICATIONS


# --- DocumentTypeConfig validation ---


def test_document_type_config_frozen():
    config = DocumentTypeConfig(id_field="Test ID")
    with pytest.raises(Exception):
        config.id_field = "Other"


def test_document_type_config_custom_chunking():
    config = DocumentTypeConfig(
        id_field="Test ID",
        chunking=ChunkingConfig(sentence_chunk_size=4000),
    )
    assert config.chunking.sentence_chunk_size == 4000
