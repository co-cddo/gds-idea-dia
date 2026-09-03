"""Tests for dia.pipeline.graph_extraction_adapter — Stage 1 output -> Document."""

from dia.pipeline.graph_extraction_adapter import BOOKKEEPING_METADATA_KEYS, to_document
from dia.pipeline.models import TextExtractionOutput


def _output(**overrides) -> TextExtractionOutput:
    defaults = dict(
        key="files/report.pdf",
        source_name="gats-business-cases",
        content_type="application/pdf",
        version='"etag-abc123"',
        text="This is the extracted document text.",
        chars=37,
        metadata={"department": "Home Office", "alb": "National Crime Agency"},
        extracted_at="2026-07-23T10:00:00+00:00",
        code_version="0.1.20",
    )
    defaults.update(overrides)
    return TextExtractionOutput(**defaults)


def test_doc_id_is_the_document_key():
    document = to_document(_output())
    assert document.doc_id == "files/report.pdf"


def test_text_is_preserved_exactly():
    document = to_document(_output(text="exact text"))
    assert document.text == "exact text"


def test_domain_metadata_is_visible_to_llm():
    document = to_document(_output(metadata={"department": "Home Office", "spend_id": "CS-100"}))
    content = document.get_content(metadata_mode="llm")
    assert "Home Office" in content
    assert "CS-100" in content


def test_domain_metadata_is_visible_to_embeddings():
    document = to_document(_output(metadata={"department": "Home Office"}))
    content = document.get_content(metadata_mode="embed")
    assert "Home Office" in content


def test_bookkeeping_fields_excluded_from_llm_content():
    document = to_document(_output())
    content = document.get_content(metadata_mode="llm")
    assert "0.1.20" not in content  # code_version
    assert "2026-07-23T10:00:00+00:00" not in content  # extracted_at
    assert "application/pdf" not in content  # content_type
    assert "gats-business-cases" not in content  # source_name


def test_bookkeeping_fields_excluded_from_embed_content():
    document = to_document(_output())
    content = document.get_content(metadata_mode="embed")
    assert "0.1.20" not in content
    assert "2026-07-23T10:00:00+00:00" not in content


def test_bookkeeping_fields_still_attached_for_traceability():
    """Excluded from LLM/embed content, but still present on the object itself."""
    document = to_document(_output())
    for field in BOOKKEEPING_METADATA_KEYS:
        assert field in document.metadata


def test_empty_domain_metadata_produces_no_error():
    document = to_document(_output(metadata={}))
    assert document.get_content(metadata_mode="llm")
