"""Document metadata resolution — enrichment and department filtering.

MetadataProvider is a resolved lookup of document key -> DocumentMetadata,
used both to enrich extracted text output and to filter documents by
department before processing.
"""

from dia.metadata.models import DocumentMetadata
from dia.metadata.provider import MetadataProvider

__all__ = ["DocumentMetadata", "MetadataProvider"]
