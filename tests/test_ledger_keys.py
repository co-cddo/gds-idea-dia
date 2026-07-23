"""Tests for dia.ledger.keys — shared composite key builder."""

from dia.ledger.keys import composite_key
from dia.types import DocumentReference


def test_composite_key_format():
    ref = DocumentReference(key="docs/report.pdf", content_type="application/pdf", version="etag-123")

    key = composite_key("text", "gats-business-cases", ref)

    assert key == "text#gats-business-cases#docs/report.pdf#etag-123"


def test_composite_key_different_stages_produce_different_keys():
    ref = DocumentReference(key="a.pdf", content_type="application/pdf", version="v1")

    text_key = composite_key("text", "source", ref)
    graph_key = composite_key("graph", "source", ref)

    assert text_key != graph_key
