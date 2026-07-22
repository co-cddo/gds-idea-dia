"""Document filters for the extraction pipeline."""

from dia.filters.noop import NoOpFilter
from dia.filters.protocol import DocumentFilter

__all__ = ["DocumentFilter", "NoOpFilter"]
