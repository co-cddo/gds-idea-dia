"""Factory for resolving the correct extractor by content type."""

from dia.extractors.docx import DocxExtractor
from dia.extractors.pdf import PdfExtractor
from dia.extractors.protocol import TextExtractor

_EXTRACTOR_MAP: dict[str, type] = {
    "application/pdf": PdfExtractor,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": DocxExtractor,
}


def get_extractor(content_type: str) -> TextExtractor:
    """Return the appropriate extractor for a given content type.

    Raises:
        ValueError: If the content type is not supported.
    """
    extractor_cls = _EXTRACTOR_MAP.get(content_type)
    if extractor_cls is None:
        supported = ", ".join(sorted(_EXTRACTOR_MAP.keys()))
        raise ValueError(f"Unsupported content type: {content_type!r}. Supported: {supported}")
    return extractor_cls()
