"""Document metadata resolution — enrichment and department filtering.

MetadataProvider is a resolved lookup of document key -> DocumentMetadata,
used both to enrich extracted text output and to filter documents by
department before processing.

Use load_metadata(source_name, ...) to get the right provider for a
known source — it knows which metadata strategy (GATS, historic CSV,
folder structure) applies to which source.
"""

from dia.metadata.models import DocumentMetadata
from dia.metadata.provider import MetadataProvider
from dia.metadata.registry import load_metadata

__all__ = ["DocumentMetadata", "MetadataProvider", "load_metadata"]
