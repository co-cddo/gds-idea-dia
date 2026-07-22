"""Document filters for the extraction pipeline."""

from dia.filters.department import DepartmentFilter
from dia.filters.noop import NoOpFilter
from dia.filters.protocol import DocumentFilter

__all__ = ["DepartmentFilter", "DocumentFilter", "NoOpFilter"]
