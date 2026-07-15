"""Text extraction from PDF and DOCX documents."""

from dia.extractors.docx import DocxExtractor
from dia.extractors.factory import get_extractor
from dia.extractors.pdf import PdfExtractor
from dia.extractors.protocol import TextExtractor

__all__ = [
    "DocxExtractor",
    "PdfExtractor",
    "TextExtractor",
    "get_extractor",
]
