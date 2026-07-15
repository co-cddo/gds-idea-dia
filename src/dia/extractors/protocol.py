"""Protocol definition for text extractors."""

from typing import Protocol


class TextExtractor(Protocol):
    """Protocol for extracting text from document bytes."""

    def extract(self, content: bytes) -> str:
        """Extract text content from raw document bytes."""
        ...
