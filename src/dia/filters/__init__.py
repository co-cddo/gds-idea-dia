"""Document filters for the extraction pipeline."""

from dia.filters.department import DepartmentFilter
from dia.filters.department_loader import (
    find_latest_key,
    load_csv_from_s3,
    load_latest_csv_from_s3,
)
from dia.filters.department_metadata import resolve_department_filter
from dia.filters.noop import NoOpFilter
from dia.filters.protocol import DocumentFilter

__all__ = [
    "DepartmentFilter",
    "DocumentFilter",
    "NoOpFilter",
    "find_latest_key",
    "load_csv_from_s3",
    "load_latest_csv_from_s3",
    "resolve_department_filter",
]
