"""Document source abstractions for reading from S3 and other locations."""

from dia.sources.known import KNOWN_SOURCES, get_source
from dia.sources.protocol import DocumentSource
from dia.sources.s3 import S3DocumentSource

__all__ = [
    "DocumentSource",
    "KNOWN_SOURCES",
    "S3DocumentSource",
    "get_source",
]
