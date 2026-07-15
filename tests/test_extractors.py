"""Tests for dia.extractors — PDF and DOCX text extraction."""

from pathlib import Path

import pytest

from dia.extractors import DocxExtractor, PdfExtractor, get_extractor

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def pdf_bytes() -> bytes:
    return (FIXTURES / "sample.pdf").read_bytes()


@pytest.fixture
def docx_bytes() -> bytes:
    return (FIXTURES / "sample.docx").read_bytes()


# --- PdfExtractor ---


def test_pdf_extracts_text(pdf_bytes):
    extractor = PdfExtractor()
    result = extractor.extract(pdf_bytes)

    assert "sample document for testing text extraction" in result


def test_pdf_extracts_table_as_markdown(pdf_bytes):
    extractor = PdfExtractor()
    result = extractor.extract(pdf_bytes)

    assert "| Name | Value |" in result
    assert "| Alpha | 100 |" in result
    assert "| Beta | 200 |" in result


def test_pdf_returns_string(pdf_bytes):
    extractor = PdfExtractor()
    result = extractor.extract(pdf_bytes)

    assert isinstance(result, str)


def test_pdf_empty_bytes_raises():
    extractor = PdfExtractor()
    with pytest.raises(Exception):
        extractor.extract(b"")


# --- DocxExtractor ---


def test_docx_extracts_text(docx_bytes):
    extractor = DocxExtractor()
    result = extractor.extract(docx_bytes)

    assert "sample document for testing text extraction" in result


def test_docx_extracts_table_as_markdown(docx_bytes):
    extractor = DocxExtractor()
    result = extractor.extract(docx_bytes)

    assert "| Name | Value |" in result
    assert "| Alpha | 100 |" in result
    assert "| Beta | 200 |" in result


def test_docx_returns_string(docx_bytes):
    extractor = DocxExtractor()
    result = extractor.extract(docx_bytes)

    assert isinstance(result, str)


def test_docx_empty_bytes_raises():
    extractor = DocxExtractor()
    with pytest.raises(Exception):
        extractor.extract(b"")


# --- get_extractor factory ---


def test_get_extractor_pdf():
    extractor = get_extractor("application/pdf")
    assert isinstance(extractor, PdfExtractor)


def test_get_extractor_docx():
    content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    extractor = get_extractor(content_type)
    assert isinstance(extractor, DocxExtractor)


def test_get_extractor_unsupported_raises():
    with pytest.raises(ValueError, match="Unsupported content type"):
        get_extractor("text/plain")


# --- Integration: factory + extract ---


def test_factory_pdf_extracts(pdf_bytes):
    extractor = get_extractor("application/pdf")
    result = extractor.extract(pdf_bytes)

    assert "sample document" in result
    assert "Alpha" in result


def test_factory_docx_extracts(docx_bytes):
    content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    extractor = get_extractor(content_type)
    result = extractor.extract(docx_bytes)

    assert "sample document" in result
    assert "Alpha" in result
