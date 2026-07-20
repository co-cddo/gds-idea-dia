"""Tests for dia.filters — DocumentFilter protocol and NoOpFilter."""

from dia.filters import NoOpFilter
from dia.types import DocumentReference


def test_noop_filter_passes_all_refs():
    refs = [
        DocumentReference(key="a.pdf", content_type="application/pdf", version="v1"),
        DocumentReference(
            key="b.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            version="v2",
        ),
    ]

    result = NoOpFilter().filter(refs)

    assert result == refs


def test_noop_filter_empty_list():
    result = NoOpFilter().filter([])

    assert result == []
